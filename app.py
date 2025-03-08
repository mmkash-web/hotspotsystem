from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
import routeros_api
import datetime
import traceback
import random
import threading
import time
import payhero  # Ensure this import is added

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for session management
CORS(app)  # Enable CORS for all routes

ROUTER_IP = 'server3.remotemikrotik.com'
USERNAME = 'admin'
PASSWORD = 'A35QOGURSS'
PORT = 7026
UPTIME_LIMIT = 3600  # Uptime limit in seconds (e.g., 3600 seconds for 1 hour)
LOG_FILE = 'user_logs.txt'  # Log file path

def log_event(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(log_entry + "\n")

def log_error(e):
    error_message = f"Error: {str(e)}\n{traceback.format_exc()}"
    log_event(error_message)

def get_router_connection():
    try:
        api_pool = routeros_api.RouterOsApiPool(
            ROUTER_IP, username=USERNAME, password=PASSWORD, port=PORT, plaintext_login=True
        )
        router = api_pool.get_api()
        return api_pool, router
    except routeros_api.exceptions.RouterOsApiConnectionError as e:
        log_error(e)
        return None, None

def create_mikrotik_user(username, password, profile, ip):
    api_pool, router = get_router_connection()
    if router is None:
        return False

    try:
        log_event(f"Attempting to add user {username} with profile {profile} to MikroTik")
        hotspot_users = router.get_resource('/ip/hotspot/user')
        active_users = router.get_resource('/ip/hotspot/active')

        # Add user to MikroTik hotspot
        hotspot_users.add(name=username, password=password, profile=profile)
        log_event(f"User added to MikroTik: Username {username}, Profile {profile}")

        # Force user to log in
        active_users.call('login', {'user': username, 'password': password, 'ip': ip})
        log_event(f"User {username} logged in automatically from IP {ip}")

        # Log user creation time and expiry
        creation_time = datetime.datetime.now()
        expiry_time = creation_time + datetime.timedelta(seconds=UPTIME_LIMIT)
        log_entry = f"{username},{ip},{profile},{creation_time},{expiry_time}\n"
        with open(LOG_FILE, "a") as log_file:
            log_file.write(log_entry)

        return True
    except routeros_api.exceptions.RouterOsApiCommunicationError as e:
        log_event(f"Failed to add user {username} with profile {profile} to MikroTik")
        log_error(e)
        return False
    finally:
        api_pool.disconnect()

def remove_expired_users():
    try:
        current_time = datetime.datetime.now()
        with open(LOG_FILE, "r") as file:
            lines = file.readlines()
        
        with open(LOG_FILE, "w") as file:
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    username, ip, profile, creation_time, expiry_time = parts[:5]
                    expiry_time = datetime.datetime.strptime(expiry_time, "%Y-%m-%d %H:%M:%S")
                    if current_time > expiry_time:
                        logout_mikrotik_user(username)
                        remove_mikrotik_user(username)
                        log_event(f"Removed expired user: Username {username}")
                    else:
                        file.write(line)
                else:
                    file.write(line)
    except Exception as e:
        log_error(e)

def remove_mikrotik_user(username):
    api_pool, router = get_router_connection()
    if router is None:
        return False

    try:
        log_event(f"Attempting to remove user {username} from MikroTik")
        hotspot_users = router.get_resource('/ip/hotspot/user')

        hotspot_users.remove(id=username)
        log_event(f"User {username} removed from MikroTik")

        return True
    except routeros_api.exceptions.RouterOsApiCommunicationError as e:
        log_event(f"Failed to remove user {username} from MikroTik")
        log_error(e)
        return False
    finally:
        api_pool.disconnect()

def logout_mikrotik_user(username):
    api_pool, router = get_router_connection()
    if router is None:
        return False

    try:
        log_event(f"Attempting to log out user {username} from MikroTik")
        active_users = router.get_resource('/ip/hotspot/active')

        # Fetch the user's active session ID
        active_sessions = active_users.get(user=username)
        if active_sessions:
            session_id = active_sessions[0]['.id']
            active_users.remove(id=session_id)
            log_event(f"User {username} logged out from MikroTik")
        else:
            log_event(f"No active session found for user {username}")

        return True
    except routeros_api.exceptions.RouterOsApiCommunicationError as e:
        log_event(f"Failed to log out user {username} from MikroTik")
        log_error(e)
        return False
    finally:
        api_pool.disconnect()

def schedule_user_removal():
    while True:
        remove_expired_users()
        time.sleep(3600)  # Check for expired users every hour

@app.route('/')
def home():
    return "Flask Server is Running! Use /login for user authentication."

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        ip = request.args.get('ip', 'Unknown IP')
        mac = request.args.get('mac', 'Unknown MAC')
        session['ip'] = ip
        session['mac'] = mac
        log_event(f"Received login request - IP: {ip}, MAC: {mac}")
        return render_template('login.html', ip=ip, mac=mac)

    elif request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        ip = session.get('ip', 'Unknown IP')
        mac = session.get('mac', 'Unknown MAC')
        phone = request.form.get('phone')
        profile = request.form.get('profile')

        log_event(f"Processing login - Username: {username}, IP: {ip}, MAC: {mac}")

        if not mac or mac == "Unknown MAC":
            return "Error: MAC Address Not Found!", 400

        expiry_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{mac},{ip},{phone},{profile},{expiry_date}\n"
        with open(LOG_FILE, "a") as file:
            file.write(log_entry)
        
        log_event(f"User logged: MAC {mac}, IP {ip}, Phone {phone}, Profile {profile}, Expiry Date {expiry_date}")
        return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/log-user', methods=['POST'])
def log_user_request():
    try:
        data = request.json
        mac = data.get("mac")
        ip = data.get("ip")
        phone = data.get("phone")
        profile = data.get("profile")
        expiry_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")  # User expires in 30 days

        if not mac or not phone:
            log_event("Error: MAC and phone number are required")
            return jsonify({"error": "MAC and phone number are required"}), 400

        log_entry = f"{mac},{ip},{phone},{profile},{expiry_date}\n"
        with open(LOG_FILE, "a") as file:
            file.write(log_entry)

        log_event(f"User logged: MAC {mac}, IP {ip}, Phone {phone}, Profile {profile}, Expiry Date {expiry_date}")
        return jsonify({"success": True, "message": "User details logged successfully"}), 200
    except Exception as e:
        log_error(e)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/payment-callback', methods=['POST'])
def payment_callback():
    try:
        # Log the entire request to debug if the callback is being received
        log_event(f"Payment callback received: {request.data}")

        data = request.json
        response_data = data.get("response", {})
        phone = response_data.get("Phone")
        status = response_data.get("Status")

        log_event(f"Payment callback received: Phone {phone}, Status {status}")
        log_event(f"Callback Data: {data}")

        if status == "Success":
            mac, ip, profile = find_user_by_phone(phone)
            if mac and ip:
                # Logout the old session
                logout_mikrotik_user(mac)

                # Generate a random 4-digit number for username and password
                username = password = str(random.randint(1000, 9999))
                log_event(f"Payment success for {phone}. Creating user {username} with profile {profile}")
                create_mikrotik_user(username, password, profile, ip)
                
                # Store username and password in session to display to the user
                session['username'] = username
                session['password'] = password
                session['ip'] = ip
                session['mac'] = mac

                # Remove the user's log entry from logs.txt
                remove_user_log(mac)

                return redirect(url_for('show_credentials'))
            else:
                log_event("User not found or missing IP in logs for payment success")
                return jsonify({"error": "User not found or missing IP in logs"}), 400

        log_event("Payment failed for phone " + str(phone))
        return jsonify({"error": "Payment failed"}), 400
    except Exception as e:
        log_error(e)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/show-credentials')
def show_credentials():
    username = session.get('username')
    password = session.get('password')
    ip = session.get('ip')
    mac = session.get('mac')
    if not username or not password:
        return redirect(url_for('login'))

    # Clear the session after displaying the credentials
    session.pop('username', None)
    session.pop('password', None)
    session.pop('ip', None)
    session.pop('mac', None)

    return render_template('credentials.html', username=username, password=password, ip=ip, mac=mac)

@app.route('/verifying-payment')
def verifying_payment():
    return render_template('verifying_payment.html')

@app.route('/pay', methods=['POST'])
def pay():
    try:
        data = request.get_json()
        phone = data.get('phone')
        package_amount = data.get('packageAmount')

        if not phone or not package_amount:
            return jsonify({"success": False, "message": "Phone number and package amount are required"}), 400
        
        payment_result = payhero.stk_push(phone, package_amount)
        if payment_result:
            return jsonify({"success": True, "message": "STK push sent! Enter your M-Pesa PIN.", "redirect_url": url_for('verifying_payment')}), 200
        else:
            return jsonify({"success": False, "message": "Payment processing failed."}), 500
    except Exception as e:
        log_error(e)
        return jsonify({"success": False, "message": "Internal server error"}), 500

@app.route('/admin')
def admin():
    users = []
    try:
        with open(LOG_FILE, "r") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    username, ip, phone, profile, expiry_date = parts[:5]
                    users.append({
                        "username": username,
                        "ip": ip,
                        "phone": phone,
                        "profile": profile,
                        "expiry_date": expiry_date
                    })
    except Exception as e:
        log_error(e)
    return render_template('admin.html', users=users)

def find_user_by_phone(phone):
    try:
        with open(LOG_FILE, "r") as file:
            for line in file:
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    mac, ip, logged_phone, profile, expiry_date = parts[:5]
                    if logged_phone == phone:
                        return mac, ip, profile
                else:
                    log_event(f"Unexpected log entry format: {line.strip()}")
        return None, None, None
    except Exception as e:
        log_error(e)
        return None, None, None

def remove_user_log(mac):
    try:
        with open(LOG_FILE, "r") as file:
            lines = file.readlines()

        with open(LOG_FILE, "w") as file:
            for line in lines:
                if mac not in line:
                    file.write(line)
    except Exception as e:
        log_error(e)

if __name__ == '__main__':
    # Start a background thread to remove expired users periodically
    threading.Thread(target=schedule_user_removal, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
