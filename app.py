import os
import csv
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for, session

app = Flask(__name__, template_folder='templates')

# --- PROTECTION & AUTH CONFIGURATION ---
# Flask requires a secret key to securely encrypt user session cookies
app.secret_key = "TELEMETRY_SESSION_ENCRYPTION_SALT_123" 

AUTH_USER = "RDP"
AUTH_PASS = "SJI"

# --- LONG-TERM FILE SETTINGS ---
ARCHIVE_FILE = "telemetry_archive.csv"

# --- GLOBAL LIVE MEMORY STORAGE (2-Hour Data Buffer) ---
live_buffer = []

# ========================================================
# 🔐 CRYPTOGRAPHY ENGINE (Python RC4 Translation)
# ========================================================
CRYPTO_KEY = b"MegaTelemetry123"

def rc4_decrypt(hex_string):
    try:
        data = bytearray.fromhex(hex_string)
        data_len = len(data)
        key_len = len(CRYPTO_KEY)
        
        S = list(range(256))
        j = 0
        for i in range(256):
            j = (j + S[i] + CRYPTO_KEY[i % key_len]) % 256
            S[i], S[j] = S[j], S[i]
            
        i = 0
        j = 0
        decrypted_bytes = bytearray(data_len)
        for k in range(data_len):
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            decrypted_bytes[k] = data[k] ^ S[(S[i] + S[j]) % 256]
            
        return decrypted_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"DECRYPTION_ERROR: {str(e)}"

# ========================================================
# 🔍 TELEMETRY DATA PARSER
# ========================================================
def parse_telemetry(plaintext):
    parsed_data = {}
    tokens = plaintext.split('|')
    for token in tokens:
        if ':' in token:
            key, val = token.split(':', 1)
            parsed_data[key.strip()] = val.strip()
        elif '=' in token:
            key, val = token.split('=', 1)
            parsed_data[key.strip()] = val.strip()
    return parsed_data

# ========================================================
# 💾 BACKEND CSV ARCHIVER
# ========================================================
def append_to_csv_archive(metrics):
    file_exists = os.path.isfile(ARCHIVE_FILE)
    fieldnames = ['Server_Timestamp', 'Transmitter_Time', 'Air_Temp_Humidity', 'Rain', 'TDS', 'Turb', 'LNK', 'PNG', 'Radio', 'SD', 'DHT', 'TURB', 'ESP_VCC']
    
    with open(ARCHIVE_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
            
        writer.writerow({
            'Server_Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Transmitter_Time': metrics.get('Time', '---'),
            'Air_Temp_Humidity': metrics.get('Air', '---'),
            'Rain': metrics.get('Rain', '---'),
            'TDS': metrics.get('TDS', '---'),
            'Turb': metrics.get('Turb', '---'),
            'LNK': metrics.get('LNK', '---'),
            'PNG': metrics.get('PNG', '---'),
            'Radio': metrics.get('Radio', '---'),
            'SD': metrics.get('SD', '---'),
            'DHT': metrics.get('DHT', '---'),
            'TURB': metrics.get('TURB', '---'),
            'ESP_VCC': metrics.get('esp_vcc', '---') # Added: Track local node receiver voltage
        })

# ========================================================
# 🌐 WEB ACCESS CONTROLLER ROUTES
# ========================================================

# 1. Login Logic Screen Routing
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_input = request.form.get('username')
        pass_input = request.form.get('password')
        
        if user_input == AUTH_USER and pass_input == AUTH_PASS:
            session['authenticated'] = True
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid User or Passcode combinations.")
            
    return render_template('login.html', error=None)

# 2. Frontend Dashboard Interface Route (Protected by Session checks)
@app.route('/', methods=['GET'])
def home():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('index.html')

# 3. ESP32 Ingestion Point (🔥 FIXED: Extracts JSON structure sent by your FireBeetle)
@app.route('/', methods=['POST'])
def receive_telemetry():
    global live_buffer
    
    # Check if request has structured JSON payload
    if request.is_json:
        json_data = request.get_json()
        raw_payload = json_data.get('data', '').strip()
        esp_vcc = json_data.get('esp_vcc', '---')
    else:
        # Fallback safeguard in case standard plaintext is transmitted
        raw_payload = request.data.decode('utf-8').strip()
        esp_vcc = '---'
    
    if not raw_payload:
        return jsonify({"status": "error", "message": "Empty payload string"}), 400
        
    # Safely decrypt the isolated raw hex payload
    decrypted_str = rc4_decrypt(raw_payload)
    metrics = parse_telemetry(decrypted_str)
    
    # Store ESP power status alongside decrypted matrix values
    metrics['esp_vcc'] = str(esp_vcc)
    
    now = datetime.now()
    try:
        append_to_csv_archive(metrics)
    except Exception as e:
        print(f"[ARCHIVE ERROR]: {e}")

    live_buffer.append({"timestamp": now, "metrics": metrics})
    
    # Prune elements older than two hours to keep RAM footprints optimized
    two_hours_ago = now - timedelta(hours=2)
    live_buffer = [packet for packet in live_buffer if packet["timestamp"] > two_hours_ago]
    
    return jsonify({"status": "success", "processed": True}), 200

# 4. Frontend Live Data API Hook (Protected by Session checks)
@app.route('/api/live', methods=['GET'])
def get_live_data():
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    if len(live_buffer) > 0:
        latest_packet = live_buffer[-1]
        return jsonify({"status": "nominal", "metrics": latest_packet["metrics"]}), 200
    else:
        return jsonify({"status": "waiting_for_data", "metrics": {}}), 200

# 5. Backup Download Route (Protected by Session checks)
@app.route('/download/archive', methods=['GET'])
def download_archive():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
        
    if os.path.isfile(ARCHIVE_FILE):
        from flask import send_file
        return send_file(ARCHIVE_FILE, as_attachment=True)
    return "No archive history available yet.", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
import csv
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for, session

app = Flask(__name__, template_folder='templates')

# --- PROTECTION & AUTH CONFIGURATION ---
# Flask requires a secret key to securely encrypt user session cookies
app.secret_key = "TELEMETRY_SESSION_ENCRYPTION_SALT_123" 

AUTH_USER = "RDP"
AUTH_PASS = "SJI"

# --- LONG-TERM FILE SETTINGS ---
ARCHIVE_FILE = "telemetry_archive.csv"

# --- GLOBAL LIVE MEMORY STORAGE (2-Hour Data Buffer) ---
live_buffer = []

# ========================================================
# 🔐 CRYPTOGRAPHY ENGINE (Python RC4 Translation)
# ========================================================
CRYPTO_KEY = b"MegaTelemetry123"

def rc4_decrypt(hex_string):
    try:
        data = bytearray.fromhex(hex_string)
        data_len = len(data)
        key_len = len(CRYPTO_KEY)
        
        S = list(range(256))
        j = 0
        for i in range(256):
            j = (j + S[i] + CRYPTO_KEY[i % key_len]) % 256
            S[i], S[j] = S[j], S[i]
            
        i = 0
        j = 0
        decrypted_bytes = bytearray(data_len)
        for k in range(data_len):
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            decrypted_bytes[k] = data[k] ^ S[(S[i] + S[j]) % 256]
            
        return decrypted_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"DECRYPTION_ERROR: {str(e)}"

# ========================================================
# 🔍 TELEMETRY DATA PARSER
# ========================================================
def parse_telemetry(plaintext):
    parsed_data = {}
    tokens = plaintext.split('|')
    for token in tokens:
        if ':' in token:
            key, val = token.split(':', 1)
            parsed_data[key.strip()] = val.strip()
        elif '=' in token:
            key, val = token.split('=', 1)
            parsed_data[key.strip()] = val.strip()
    return parsed_data

# ========================================================
# 📂 BACKEND CSV ARCHIVER
# ========================================================
def append_to_csv_archive(metrics):
    file_exists = os.path.isfile(ARCHIVE_FILE)
    fieldnames = ['Server_Timestamp', 'Transmitter_Time', 'Air_Temp_Humidity', 'Rain', 'TDS', 'Turb', 'LNK', 'PNG', 'Radio', 'SD', 'DHT', 'TURB']
    
    with open(ARCHIVE_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
            
        writer.writerow({
            'Server_Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Transmitter_Time': metrics.get('Time', '---'),
            'Air_Temp_Humidity': metrics.get('Air', '---'),
            'Rain': metrics.get('Rain', '---'),
            'TDS': metrics.get('TDS', '---'),
            'Turb': metrics.get('Turb', '---'),
            'LNK': metrics.get('LNK', '---'),
            'PNG': metrics.get('PNG', '---'),
            'Radio': metrics.get('Radio', '---'),
            'SD': metrics.get('SD', '---'),
            'DHT': metrics.get('DHT', '---'),
            'TURB': metrics.get('TURB', '---')
        })

# ========================================================
# 🌐 WEB ACCESS CONTROLLER ROUTES
# ========================================================

# 1. Login Logic Screen Routing
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_input = request.form.get('username')
        pass_input = request.form.get('password')
        
        if user_input == AUTH_USER and pass_input == AUTH_PASS:
            session['authenticated'] = True
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid User or Passcode combinations.")
            
    return render_template('login.html', error=None)

# 2. Frontend Dashboard Interface Route (Protected by Session checks)
@app.route('/', methods=['GET'])
def home():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('index.html')

# 3. ESP32 Ingestion Point (Always Open, no cookie check so FireBeetle can POST data)
@app.route('/', methods=['POST'])
def receive_telemetry():
    global live_buffer
    raw_payload = request.data.decode('utf-8').strip()
    
    if not raw_payload:
        return jsonify({"status": "error", "message": "Empty payload"}), 400
        
    decrypted_str = rc4_decrypt(raw_payload)
    metrics = parse_telemetry(decrypted_str)
    
    now = datetime.now()
    try:
        append_to_csv_archive(metrics)
    except Exception as e:
        print(f"[ARCHIVE ERROR]: {e}")

    live_buffer.append({"timestamp": now, "metrics": metrics})
    
    two_hours_ago = now - timedelta(hours=2)
    live_buffer = [packet for packet in live_buffer if packet["timestamp"] > two_hours_ago]
    
    return jsonify({"status": "success", "processed": True}), 200

# 4. Frontend Live Data API Hook (Protected by Session checks)
@app.route('/api/live', methods=['GET'])
def get_live_data():
    if not session.get('authenticated'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    if len(live_buffer) > 0:
        latest_packet = live_buffer[-1]
        return jsonify({"status": "nominal", "metrics": latest_packet["metrics"]}), 200
    else:
        return jsonify({"status": "waiting_for_data", "metrics": {}}), 200

# 5. Backup Download Route (Protected by Session checks)
@app.route('/download/archive', methods=['GET'])
def download_archive():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
        
    if os.path.isfile(ARCHIVE_FILE):
        from flask import send_file
        return send_file(ARCHIVE_FILE, as_attachment=True)
    return "No archive history available yet.", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
