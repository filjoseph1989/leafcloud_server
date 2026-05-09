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

# --- CONFIGURATION (WINDOWS/WSL OPTIMIZED) ---
EC_K_VALUE = 6.04
HYBRID_PH_VALUE = 0  # Centralized simulated pH value

# Hardcoded pH Calibration (Multi-point Range)
CAL_POINTS = [
    (2.487, 7.00),  # Tap Water
    (2.508, 6.86),  # Buffer 6.86
    (2.931, 4.01)   # Buffer 4.01
]

CALIBRATION_FILE = "calibration_config.json"

# Server Configuration
# For Windows/WSL, we use the Reverse TCP strategy.
# SERVER_IP should be the IP of your Raspberry Pi when it is in --listen mode.
SERVER_IP = os.getenv("SERVER_IP", "192.168.1.5") 
FASTAPI_URL = f"http://{SERVER_IP}:8000/iot/sensor_data/" # Note: This script usually runs ON the Pi
CONTROL_URL = f"http://{SERVER_IP}:8000/control/current-status"

# --- WINDOWS/WSL SPECIAL CAMERA COMMAND ---
# On Windows/WSL, we use TCP Listen mode to bypass NAT/Firewall issues.
# The Pi will wait for the Windows machine to connect.
CAMERA_CMD = "rpicam-vid -t 0 --inline -g 30 --flush --listen -o tcp://0.0.0.0:5000"

def save_calibration():
    """Persists the current calibration values to a local file."""
    global EC_K_VALUE, CAL_POINTS
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump({
                "EC_K_VALUE": EC_K_VALUE,
                "CAL_POINTS": CAL_POINTS
            }, f)
        print(f"💾 Calibration saved to {CALIBRATION_FILE}")
    except Exception as e:
        print(f"❌ Failed to save calibration: {e}")

def load_calibration():
    """Loads calibration values from a local file if it exists."""
    global EC_K_VALUE, CAL_POINTS
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                EC_K_VALUE = data.get("EC_K_VALUE", EC_K_VALUE)
                # JSON converts tuples to lists, so we convert them back to tuples
                raw_points = data.get("CAL_POINTS", [])
                if raw_points:
                    CAL_POINTS = [tuple(p) for p in raw_points]
                print(f"📂 Calibration loaded from {CALIBRATION_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to load calibration, using defaults: {e}")

def get_ph_value(voltage):
    """Calculates pH value from voltage using a linear interpolation."""
    if voltage < 0.2:  # Likely disconnected or failing probe
        return -1.0
    points = sorted(CAL_POINTS)
    if voltage <= points[0][0]:
        v1, p1 = points[0]
        v2, p2 = points[1]
    elif voltage >= points[-1][0]:
        v1, p1 = points[-2]
        v2, p2 = points[-1]
    else:
        v1, p1, v2, p2 = points[0][0], points[0][1], points[1][0], points[1][1]
        for i in range(len(points) - 1):
            if points[i][0] <= voltage <= points[i + 1][0]:
                v1, p1 = points[i]
                v2, p2 = points[i + 1]
                break
    slope = (p2 - p1) / (v2 - v1)
    ph_value = p1 + (voltage - v1) * slope
    return max(0.0, min(14.0, ph_value))

def get_temp_device_file():
    """Locates the DS18B20 temperature sensor device file."""
    base_dir = '/sys/bus/w1/devices/'
    device_folders = glob.glob(base_dir + '28*')
    if not device_folders:
        return None
    return device_folders[0] + '/w1_slave'

TEMP_DEVICE_FILE = get_temp_device_file()

def read_temp_raw(file_path):
    """Reads the raw temperature file content."""
    try:
        with open(file_path, 'r') as f:
            return f.readlines()
    except Exception:
        return []

def read_temperature():
    """Parses and returns the temperature in Celsius from the DS18B20."""
    if not TEMP_DEVICE_FILE:
        return None
    try:
        lines = read_temp_raw(TEMP_DEVICE_FILE)
        if not lines:
            return None
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            lines = read_temp_raw(TEMP_DEVICE_FILE)
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            temp_string = lines[1][equals_pos + 2:]
            return float(temp_string) / 1000.0
    except Exception:
        return None
    return None

def get_active_command():
    """Checks the server for an active command."""
    # Note: On Pi, SERVER_IP should be the address of the machine running FastAPI.
    # If this script is running ON the Pi, and it needs to talk to WSL, 
    # it must use the WSL machine's LAN IP.
    try:
        # Assuming you've set SERVER_IP to the Windows/WSL host LAN IP
        response = requests.get(CONTROL_URL, timeout=2.0)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def check_for_quit():
    """Checks if 'q' was pressed on stdin without blocking."""
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        key = sys.stdin.read(1)
        if key.lower() == 'q':
            return True
    return False

def handle_restart(cam_proc):
    """Acknowledge restart signal from server and restart the script."""
    print("\n⚠️ Restart requested by server. Acknowledging and restarting...")
    try:
        ACK_URL = f"http://{SERVER_IP}:8000/control/acknowledge-restart"
        requests.post(ACK_URL, timeout=2.0)
    except Exception as e:
        print(f"Failed to acknowledge restart: {e}")
    stop_camera(cam_proc)
    print("Restarting script now...")
    time.sleep(1.0)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def start_camera():
    """Starts the camera stream in TCP Listen mode for Windows/WSL."""
    print(f"📸 Starting Camera Stream (TCP Listen on 0.0.0.0:5000)...")
    print(f"💡 Server should connect to tcp://PI_IP:5000")
    try:
        cam_proc = subprocess.Popen(
            CAMERA_CMD,
            shell=True,
            preexec_fn=os.setsid,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        logs_done = threading.Event()
        def monitor_camera(proc, event):
            count = 0
            for line in iter(proc.stdout.readline, ''):
                if count < 5:
                    print(f"[Camera] {line.strip()}")
                    count += 1
                    if count == 5:
                        event.set()
            event.set()
        threading.Thread(target=monitor_camera, args=(cam_proc, logs_done), daemon=True).start()
        logs_done.wait(timeout=5.0)
        return cam_proc
    except Exception as e:
        print(f"❌ Failed to start camera: {e}")
        return None

def stop_camera(cam_proc):
    """Stops the camera stream background process."""
    if cam_proc:
        try:
            print("🛑 Stopping camera stream...")
            os.killpg(os.getpgid(cam_proc.pid), 9)
        except Exception:
            pass
    return None

def main():
    """Main execution loop for sensor data collection and streaming."""
    load_calibration()
    cam_proc = start_camera()
    ph_update_mode_active = False

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ec_chan = AnalogIn(ads, 0)
        ph_chan = AnalogIn(ads, 0)
    except Exception as e:
        print(f"Error initializing I2C/ADS1115: {e}")
        if cam_proc: stop_camera(cam_proc)
        return

    print("Starting Combined Sensor Monitor & Data Streamer (WINDOWS VERSION)...")
    print(f"FastAPI Endpoint: {FASTAPI_URL}")
    print("-" * 75)

    try:
        while True:
            if check_for_quit(): break
            active_command = get_active_command()
            if active_command and active_command.get("restart_requested"):
                handle_restart(cam_proc)

            bucket_id = active_command.get("active_bucket_id", None) if active_command else None
            experiment_id = active_command.get("active_experiment_id", None) if active_command else None
            ph_update_requested = active_command.get("ph_update_requested", False) if active_command else False
            
            calibration_active = ph_update_requested or active_command.get("ec_calibration_requested", False) if active_command else False

            if calibration_active and not ph_update_mode_active:
                cam_proc = stop_camera(cam_proc)
                ph_update_mode_active = True
            elif not calibration_active and ph_update_mode_active:
                cam_proc = start_camera()
                ph_update_mode_active = False

            temp = read_temperature()
            temp_val = temp if temp is not None else 0.0
            
            # Sampling
            ec_readings = [ec_chan.voltage for _ in range(20)]
            ph_readings = [ph_chan.voltage for _ in range(20)]
            avg_ec_voltage = statistics.median(ec_readings)
            avg_ph_voltage = statistics.median(ph_readings)

            ec_value = avg_ec_voltage * EC_K_VALUE
            current_ph = get_ph_value(avg_ph_voltage) if not ph_update_requested else HYBRID_PH_VALUE

            # Display and send logic...
            print(f"Temp: {temp_val:.2f} | EC: {ec_value:.2f} | pH: {current_ph:.2f}")
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_camera(cam_proc)

if __name__ == "__main__":
    main()
