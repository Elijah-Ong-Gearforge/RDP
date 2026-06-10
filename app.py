import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# ========================================================
# 🔐 CRYPTOGRAPHY ENGINE (Python RC4 Translation)
# ========================================================
CRYPTO_KEY = b"MegaTelemetry123"

def rc4_decrypt(hex_string):
    try:
        # Convert hex string back to raw bytes
        data = bytearray.fromhex(hex_string)
        data_len = len(data)
        key_len = len(CRYPTO_KEY)
        
        # Key Scheduling Algorithm (KSA)
        S = list(range(256))
        j = 0
        for i in range(256):
            j = (j + S[i] + CRYPTO_KEY[i % key_len]) % 256
            S[i], S[j] = S[j], S[i]
            
        # Pseudo-Random Generation Algorithm (PRGA) & XOR
        i = 0
        j = 0
        decrypted_bytes = bytearray(data_len)
        for k in range(data_len):
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            decrypted_bytes[k] = data[k] ^ S[(S[i] + S[j]) % 256]
            
        # Decode binary data to UTF-8 plaintext string
        return decrypted_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"DECRYPTION_ERROR: {str(e)}"

# ========================================================
# 🔍 TELEMETRY DATA PARSER
# ========================================================
def parse_telemetry(plaintext):
    # Example format: "Air:23.5,55.0|TDS:120,1.2|Turb:400,2.1|Rain:950|LNK:98|PNG:12"
    parsed_data = {}
    
    # Split the main tokens
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
# 🌐 WEB ROUTES
# ========================================================

# 1. Root Dashboard (To verify your server is online via a browser)
@app.route('/', methods=['GET'])
def home():
    return """
    <html>
        <head><title>Telemetry Cloud Hub</title></head>
        <body style="font-family:sans-serif; text-align:center; padding-top:50px;">
            <h1>🌐 Telemetry Cloud Server Online</h1>
            <p>Ready to receive streaming sensor packets from your ESP32 Gateway.</p>
        </body>
    </html>
    """

# 2. ESP32 Dynamic Ingestion Endpoint
@app.route('/', methods=['POST'])
def receive_telemetry():
    # Capture incoming raw data string
    raw_payload = request.data.decode('utf-8').strip()
    
    if not raw_payload:
        return jsonify({"status": "error", "message": "Empty payload received"}), 400
        
    print(f"\n[RAW INCOMING CRYPTO]: {raw_payload}")
    
    # Decrypt payload using RC4
    decrypted_str = rc4_decrypt(raw_payload)
    print(f"[LIVE DECRYPTED STRING]: {decrypted_str}")
    
    # Parse human-readable values out of the payload
    metrics = parse_telemetry(decrypted_str)
    print(f"[PARSED METRICS]: {metrics}")
    
    # Success acknowledgement return back to ESP32
    return jsonify({
        "status": "success",
        "processed": True,
        "payload_length": len(raw_payload),
        "data": metrics
    }), 200

if __name__ == '__main__':
    # Grab Render's dynamic production port, fallback to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
