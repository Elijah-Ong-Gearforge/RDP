import os
import csv
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='templates')

# --- LONG-TERM FILE SETTINGS ---
ARCHIVE_FILE = "telemetry_archive.csv"

# --- GLOBAL LIVE MEMORY STORAGE (Holds list of data points for the last 2 hours) ---
# Format: [{"timestamp": datetime_obj, "metrics": {...}}, ...]
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
    
    # Define your standard Excel column headers
    fieldnames = ['Server_Timestamp', 'Transmitter_Time', 'Air_Temp_Humidity', 'Rain', 'TDS', 'Turb', 'LNK', 'PNG', 'Radio', 'SD', 'DHT', 'TURB']
    
    with open(ARCHIVE_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # If the server just restarted or file is brand new, write Excel headers first
        if not file_exists:
            writer.writeheader()
            
        # Map incoming data tokens smoothly to table slots
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
# 🌐 WEB ROUTES
# ========================================================

# 1. Frontend Dashboard Interface
@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

# 2. ESP32 Ingestion Pipeline (Processes entries, appends to CSV, cleans old live cache)
@app.route('/', methods=['POST'])
def receive_telemetry():
    global live_buffer
    raw_payload = request.data.decode('utf-8').strip()
    
    if not raw_payload:
        return jsonify({"status": "error", "message": "Empty payload"}), 400
        
    # Decrypt and parse incoming packet
    decrypted_str = rc4_decrypt(raw_payload)
    metrics = parse_telemetry(decrypted_str)
    
    now = datetime.now()
    
    # A. Commit directly to permanent Excel/CSV archive array
    try:
        append_to_csv_archive(metrics)
    except Exception as e:
        print(f"[ARCHIVE ERROR]: Failed to write log entries: {e}")

    # B. Add packet to the temporary live dashboard list
    live_buffer.append({
        "timestamp": now,
        "metrics": metrics
    })
    
    # C. AUTOMATIC WIPE: Remove data elements older than exactly 2 hours
    two_hours_ago = now - timedelta(hours=2)
    live_buffer = [packet for packet in live_buffer if packet["timestamp"] > two_hours_ago]
    
    return jsonify({"status": "success", "processed": True}), 200

# 3. Frontend Live Data API Hook (Returns only the latest valid packet from cache)
@app.route('/api/live', methods=['GET'])
def get_live_data():
    if len(live_buffer) > 0:
        # Grab the newest packet sitting at the end of our 2-hour queue
        latest_packet = live_buffer[-1]
        return jsonify({
            "status": "nominal",
            "metrics": latest_packet["metrics"]
        }), 200
    else:
        return jsonify({
            "status": "waiting_for_data",
            "metrics": {}
        }), 200

# 4. Hidden Download Route (Allows you to pull down your backup Excel file anytime)
@app.route('/download/archive', methods=['GET'])
def download_archive():
    if os.path.isfile(ARCHIVE_FILE):
        from flask import send_file
        return send_file(ARCHIVE_FILE, as_attachment=True)
    return "No archive history available yet.", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
