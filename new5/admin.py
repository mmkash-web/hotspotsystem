from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin, expose, AdminIndexView
from flask_admin.contrib.sqla import ModelView
import routeros_api
import datetime
import payhero
import traceback
import random
import threading

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for session management
CORS(app)  # Enable CORS for all routes

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# MikroTik configuration
ROUTER_IP = "192.168.88.1"
USERNAME = "admin"
PASSWORD = "A35QOGURSS"
LOG_FILE = "user_logs.txt"

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mac = db.Column(db.String(17), unique=True, nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    profile = db.Column(db.String(50), nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

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
        expired_users = User.query.filter(User.expiry_date < current_time).all()
        for user in expired_users:
            logout_mikrotik_user(user.mac)
            remove_mikrotik_user(user.mac)
            log_event(f"Removed expired user: MAC {user.mac}")
            db.session.delete(user)
        db.session.commit()
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
        log_event(f"Received login request - IP: {ip}, MAC: {mac}")
        return render_template('login.html', ip=ip, mac=mac)

    elif request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        ip = request.form.get('ip')
        mac = request.form.get('mac')

        log_event(f"Processing login - Username: {username}, IP: {ip}, MAC: {mac}")

        if not mac or mac == "Unknown MAC":
            return "Error: MAC Address Not Found!", 400

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

        user = User(mac=mac, ip=ip, phone=phone, profile=profile, expiry_date=expiry_date)
        db.session.add(user)
        db.session.commit()

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
        amount = response_data.get("Amount", 0.0)

        log_event(f"Payment callback received: Phone {phone}, Status {status}, Amount {amount}")
        log_event(f"Callback Data: {data}")

        payment = Payment(phone=phone, amount=amount, status=status)
        db.session.add(payment)
        db.session.commit()

        if status == "Success":
            mac, ip, profile = find_user_by_phone(phone)
            if mac:
                # Use last 4 digits of the phone number and mix them to create username and password
                last_four_digits = list(phone[-4:])
                random.shuffle(last_four_digits)
                username = ''.join(last_four_digits)
                password = username
                log_event(f"Payment success for {phone}. Creating user {username} with profile {profile}")
                create_mikrotik_user(username, password, profile, ip)
                
                # Store username and password in session to display to the user
                session['username'] = username
                session['password'] = password
                return redirect(url_for('show_credentials'))
            log_event("User not found in logs for payment success")
            return jsonify({"error": "User not found in logs"}), 400

        log_event("Payment failed for phone " + str(phone))
        return jsonify({"error": "Payment failed"}), 400
    except Exception as e:
        log_error(e)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/show-credentials')
def show_credentials():
    username = session.get('username')
    password = session.get('password')
    if not username or not password:
        return redirect(url_for('login'))

    # Clear the session after displaying the credentials
    session.pop('username', None)
    session.pop('password', None)

    return render_template('credentials.html', username=username, password=password)

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

def find_user_by_phone(phone):
    try:
        user = User.query.filter_by(phone=phone).first()
        if user:
            return user.mac, user.ip, user.profile
        return None, None, None
    except Exception as e:
        log_error(e)
        return None, None, None

# Admin views
class UserAdmin(ModelView):
    column_list = ('mac', 'ip', 'phone', 'profile', 'expiry_date')
    form_columns = ('mac', 'ip', 'phone', 'profile', 'expiry_date')

class PaymentAdmin(ModelView):
    column_list = ('phone', 'amount', 'status', 'timestamp')
    form_columns = ('phone', 'amount', 'status')

class LogAdmin(AdminIndexView):
    @expose('/')
    def index(self):
        with open(LOG_FILE, 'r') as log_file:
            logs = log_file.readlines()
        return self.render('admin/logs.html', logs=logs)

# Initialize Flask-Admin
admin = Admin(app, name='Admin Panel', template_mode='bootstrap3', index_view=LogAdmin())
admin.add_view(UserAdmin(User, db.session))
admin.add_view(PaymentAdmin(Payment, db.session))

if __name__ == '__main__':
    # Start a background thread to remove expired users periodically
    threading.Thread(target=schedule_user_removal, daemon=True).start()
    db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)