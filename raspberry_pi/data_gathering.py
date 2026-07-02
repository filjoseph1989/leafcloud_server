import os
import sys
import glob
import time
import json
import threading
import statistics
import subprocess
import requests
import board
import busio
from datetime import datetime
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import select
from discovery_client import discover_server

# --- CONFIGURATION ---
EC_K_VALUE = 6.04
HYBRID_PH_VALUE = 0  # Centralized simulated pH value

# Hardcoded pH Calibration (Multi-point Range)
CAL_POINTS = [
    (2.487, 7.00),  # Tap Water
    (2.508, 6.86),  # Buffer 6.86
    (2.931, 4.01)   # Buffer 4.01
]

CALIBRATION_FILE = "calibration_config.json"

def get_server_config():
    """Discovers the server and returns the base URL and IP."""
    print("🔍 Searching for LeafCloud Server...")
    url = discover_server(timeout=15)
    if url:
        # Extract IP for camera stream (udp)
        # url is http://192.168.1.50:8000
        ip = url.split("//")[1].split(":")[0]
        return url, ip
    
    print("⚠️ Discovery failed. Falling back to localhost/env settings.")
    env_ip = os.getenv("SERVER_IP", "192.168.1.10")
    return f"http://{env_ip}:8000", env_ip

SERVER_URL, SERVER_IP = get_server_config()

# API Endpoints derived from discovery
FASTAPI_URL = f"{SERVER_URL}/api/v1/iot/sensor_data/" # Note: Updated path to match V2 schema if necessary
CONTROL_URL = f"{SERVER_URL}/api/v1/iot/control/current-status"

# Camera stream command (UDP to Server)
CAMERA_CMD = f"rpicam-vid -t 0 --inline -g 30 --flush --codec h264 --width 640 --height 480 --framerate 30 -o udp://{SERVER_IP}:5000"

def save_calibration():
    global EC_K_VALUE, CAL_POINTS
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump({"EC_K_VALUE": EC_K_VALUE, "CAL_POINTS": CAL_POINTS}, f)
        print(f"💾 Calibration saved to {CALIBRATION_FILE}")
    except Exception as e:
        print(f"❌ Failed to save calibration: {e}")

def load_calibration():
    global EC_K_VALUE, CAL_POINTS
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                EC_K_VALUE = data.get("EC_K_VALUE", EC_K_VALUE)
                raw_points = data.get("CAL_POINTS", [])
                if raw_points:
                    CAL_POINTS = [tuple(p) for p in raw_points]
                print(f"📂 Calibration loaded from {CALIBRATION_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to load calibration, using defaults: {e}")

def get_ph_value(voltage):
    if voltage < 0.2: return -1.0
    points = sorted(CAL_POINTS)
    if voltage <= points[0][0]:
        v1, p1 = points[0]; v2, p2 = points[1]
    elif voltage >= points[-1][0]:
        v1, p1 = points[-2]; v2, p2 = points[-1]
    else:
        v1, p1, v2, p2 = points[0][0], points[0][1], points[1][0], points[1][1]
        for i in range(len(points) - 1):
            if points[i][0] <= voltage <= points[i + 1][0]:
                v1, p1 = points[i]; v2, p2 = points[i + 1]; break
    slope = (p2 - p1) / (v2 - v1)
    ph_value = p1 + (voltage - v1) * slope
    return max(0.0, min(14.0, ph_value))

def get_temp_device_file():
    base_dir = '/sys/bus/w1/devices/'
    device_folders = glob.glob(base_dir + '28*')
    return device_folders[0] + '/w1_slave' if device_folders else None

TEMP_DEVICE_FILE = get_temp_device_file()

def read_temperature():
    if not TEMP_DEVICE_FILE: return None
    try:
        with open(TEMP_DEVICE_FILE, 'r') as f: lines = f.readlines()
        if not lines or lines[0].strip()[-3:] != 'YES': return None
        equals_pos = lines[1].find('t=')
        return float(lines[1][equals_pos + 2:]) / 1000.0 if equals_pos != -1 else None
    except Exception: return None

def get_active_command():
    try:
        response = requests.get(CONTROL_URL, timeout=2.0)
        return response.json() if response.status_code == 200 else None
    except Exception: return None

def check_for_quit():
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        key = sys.stdin.read(1); return key.lower() == 'q'
    return False

def handle_restart(cam_proc):
    print("\n⚠️ Restart requested by server. Acknowledging and restarting...")
    try:
        ACK_URL = f"{SERVER_URL}/api/v1/iot/control/acknowledge-restart"
        requests.post(ACK_URL, timeout=2.0)
    except Exception as e: print(f"Failed to acknowledge restart: {e}")
    stop_camera(cam_proc)
    time.sleep(1.0)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def start_camera():
    print(f"📸 Starting Camera Stream (UDP to {SERVER_IP}:5000)...")
    try:
        cam_proc = subprocess.Popen(CAMERA_CMD, shell=True, preexec_fn=os.setsid, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        logs_done = threading.Event()
        def monitor_camera(proc, event):
            count = 0
            for line in iter(proc.stdout.readline, ''):
                if count < 5: print(f"[Camera] {line.strip()}"); count += 1; 
                if count == 5: event.set()
            event.set()
        threading.Thread(target=monitor_camera, args=(cam_proc, logs_done), daemon=True).start()
        logs_done.wait(timeout=5.0); return cam_proc
    except Exception as e: print(f"❌ Failed to start camera: {e}"); return None

def stop_camera(cam_proc):
    if cam_proc:
        try:
            print("🛑 Stopping camera stream...")
            os.killpg(os.getpgid(cam_proc.pid), 9)
        except Exception: pass
    return None

def main():
    global EC_K_VALUE, CAL_POINTS
    load_calibration()
    cam_proc = start_camera()
    try:
        i2c = busio.I2C(board.SCL, board.SDA); ads = ADS.ADS1115(i2c)
        ec_chan = AnalogIn(ads, 0); ph_chan = AnalogIn(ads, 0)
    except Exception as e:
        print(f"Error initializing I2C/ADS1115: {e}"); stop_camera(cam_proc); return

    print("Starting Combined Sensor Monitor & Data Streamer...")
    print("-" * 75)
    print(f"{'Temp (°C)':>12} | {'EC (mS/cm)':>12} | {'pH Level':>12} | {'Local Status':>12} | {'Server Status'}")
    print("-" * 75)

    try:
        while True:
            if check_for_quit(): break
            active_command = get_active_command()
            if active_command and active_command.get("restart_requested"): handle_restart(cam_proc)
            
            # Simplified for V2 logic: check server state for maintenance
            # You can also fetch specific calibration IDs from the /calibration endpoint here if needed
            
            temp = read_temperature()
            temp_val = temp if temp is not None else 0.0
            
            ec_readings = []; ph_readings = []
            for _ in range(20):
                ec_readings.append(ec_chan.voltage); ph_readings.append(ph_chan.voltage); time.sleep(0.02)
            avg_ec_voltage = statistics.median(ec_readings); avg_ph_voltage = statistics.median(ph_readings)

            ec_value = avg_ec_voltage * EC_K_VALUE
            current_ph = get_ph_value(avg_ph_voltage)

            payload = {
                "temperature": round(temp_val, 2),
                "ec": round(ec_value, 2),
                "ph": round(current_ph, 2),
                "timestamp": datetime.now().isoformat()
            }

            try:
                response = requests.post(FASTAPI_URL, json=payload, timeout=2.0)
                server_status = f"Sent ({response.status_code})"
            except Exception as e: server_status = "Offline"

            print(f"{temp_val:12.2f} | {ec_value:12.2f} | {current_ph:12.2f} | {'Active':>12} | {server_status}")
            time.sleep(1.0)
    finally:
        stop_camera(cam_proc)

if __name__ == "__main__":
    main()
