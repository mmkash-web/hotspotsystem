from flask import Flask, request, jsonify, render_template, redirect, url_for, session, abort
from flask_cors import CORS
import routeros_api
import datetime
import payhero
import traceback
import random
import threading
import time

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for session management
CORS(app)  # Enable CORS for all routes

ROUTER_IP = "192.168.88.1"
USERNAME = "admin"
PASSWORD = "A35QOGURSS"
LOG_FILE = "user_logs.txt"

def log_event(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(LOG_FILE, "a") as log_file:
        log_file.write(log_entry + "\n")

def log_error(e):
    error_message = f"Error: {str(e)}\n{traceback.format_exc()}"
    log_event(error_message)

def create_mikrotik_user(username, password, profile, ip):
    try:
        log_event(f"Attempting to add user {username} with profile {profile} to MikroTik")
        api = routeros_api.RouterOsApiPool(ROUTER_IP, username=USERNAME, password=PASSWORD, plaintext_login=True)
        router = api.get_api()
        hotspot_users = router.get_resource('/ip/hotspot/user')
        hotspot_profiles = router.get_resource('/ip/hotspot/user/profile')
        active_users = router.get_resource('/ip/hotspot/active')

        # Log available profiles for debugging
        available_profiles = hotspot_profiles.get()
        log_event(f"Available profiles: {available_profiles}")

        # Add user to MikroTik hotspot
        hotspot_users.add(name=username, password=password, profile=profile)
        log_event(f"User added to MikroTik: Username {username}, Profile {profile}")

        # Force user to log in
        active_users.call('login', {'user': username, 'password': password, 'ip': ip})
        log_event(f"User {username} logged in automatically from IP {ip}")

        api.disconnect()
    except routeros_api.exceptions.RouterOsApiCommunicationError as e:
        log_event(f"Failed to add user {username} with profile {profile} to MikroTik")
        log_error(e)
    except Exception as e:
        log_error(e)

def remove_expired_users():
    try:
        current_time = datetime.datetime.now()
        with open(LOG_FILE, "r") as file:
            lines = file.readlines()
        
        with open(LOG_FILE, "w") as file:
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    mac, ip, phone, profile, expiry_date = parts[:5]
                    expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
                    if current_time > expiry_date:
                        logout_mikrotik_user(mac)
                        remove_mikrotik_user(mac)
                        log_event(f"Removed expired user: MAC {mac}")
                    else:
                        file.write(line)
                else:
                    file.write(line)
    except Exception as e:
        log_error(e)

def remove_mikrotik_user(username):
    try:
        log_event(f"Attempting to remove user {username} from MikroTik")
        api = routeros_api.RouterOsApiPool(ROUTER_IP, username=USERNAME, password=PASSWORD, plaintext_login=True)
        router = api.get_api()
        hotspot_users = router.get_resource('/ip/hotspot/user')

        hotspot_users.remove(id=username)
        log_event(f"User {username} removed from MikroTik")

        api.disconnect()
    except routeros_api.exceptions.RouterOsApiCommunicationError as e:
        log_event(f"Failed to remove user {username} from MikroTik")
        log_error(e)
    except Exception as e:
        log_error(e)

def logout_mikrotik_user(username):
    try:
        log_event(f"Attempting to log out user {username} from MikroTik")
        api = routeros_api.RouterOsApiPool(ROUTER_IP, username=USERNAME, password=PASSWORD, plaintext_login=True)
        router = api.get_api()
        active_users = router.get_resource('/ip/hotspot/active')

        active_users.remove(user=username)
        log_event(f"User {username} logged out from MikroTik")

        api.disconnect()
    except routeros_api.exceptions.RouterOsApiCommunicationError as e:
        log_event(f"Failed to log out user {username} from MikroTik")
        log_error(e)
    except Exception as e:
        log_error(e)

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
        return "Login successful!"

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
            return jsonify({"success": True, "message": "STK push sent! Enter your M-Pesa PIN."}), 200
        else:
            return jsonify({"success": False, "message": "Payment processing failed."}), 500
    except Exception as e:
        log_error(e)
        return jsonify({"success": False, "message": "Internal server error"}), 500

@app.route('/login-success.html')
def block_login_success():
    abort(404)

if __name__ == '__main__':
    # Start a background thread to remove expired users periodically
    threading.Thread(target=schedule_user_removal, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
