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

# Server Configuration
# Prefer environment variable, else default to 192.168.1.10
SERVER_IP = os.getenv("SERVER_IP", "192.168.1.10")
FASTAPI_URL = f"http://{SERVER_IP}:8000/iot/sensor_data/"
CONTROL_URL = f"http://{SERVER_IP}:8000/control/current-status"

# Camera stream command (UDP to Server)
# -g 30 ensures a keyframe every second. --flush helps WSL handle UDP packets more reliably.
CAMERA_CMD = f"rpicam-vid -t 0 --inline -g 30 --flush --codec h264 --width 640 --height 480 --framerate 30 -o udp://{SERVER_IP}:5000"

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
    """Calculates pH value from voltage using a linear interpolation.

    Args:
        voltage (float): The measured voltage from the sensor.

    Returns:
        float: The calculated pH value (0-14).
    """
    if voltage < 0.2:  # Likely disconnected or failing probe
        return -1.0

    # Sort points by voltage
    points = sorted(CAL_POINTS)

    # Find the segment for interpolation
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

    # Interpolation calculation
    slope = (p2 - p1) / (v2 - v1)
    ph_value = p1 + (voltage - v1) * slope

    # Clamp to physical limits (0-14)
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
    """Checks the MacBook FastAPI server for an active command.

    Returns:
        dict: The response JSON if successful, or None otherwise.
    """
    try:
        response = requests.get(CONTROL_URL, timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            return data
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
    """Acknowledge restart signal from server and restart the script.

    Args:
        cam_proc (subprocess.Popen): The current camera process.
    """
    print("\n⚠️ Restart requested by server. Acknowledging and restarting...")
    try:
        # 1. Acknowledge
        ACK_URL = f"http://{SERVER_IP}:8000/control/acknowledge-restart"
        requests.post(ACK_URL, timeout=2.0)
    except Exception as e:
        print(f"Failed to acknowledge restart: {e}")

    # 2. Cleanup camera
    stop_camera(cam_proc)

    # 3. Restart script
    print("Restarting script now...")
    time.sleep(1.0)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def start_camera():
    """Starts the camera stream in the background.

    Returns:
        subprocess.Popen: The camera process instance, or None on failure.
    """
    print(f"📸 Starting Camera Stream (UDP to {SERVER_IP}:5000)...")
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

        # Event to signal when initial logs are done
        logs_done = threading.Event()

        # Print only the first 5 lines of camera status
        def monitor_camera(proc, event):
            count = 0
            for line in iter(proc.stdout.readline, ''):
                if count < 5:
                    print(f"[Camera] {line.strip()}")
                    count += 1
                    if count == 5:
                        event.set()
                # Keep reading the pipe to prevent the process from blocking
            event.set() # Ensure we don't block forever if process ends early
        threading.Thread(target=monitor_camera, args=(cam_proc, logs_done), daemon=True).start()

        # Wait for the first 5 lines or timeout
        logs_done.wait(timeout=5.0)
        return cam_proc
    except Exception as e:
        print(f"❌ Failed to start camera: {e}")
        return None

def stop_camera(cam_proc):
    """Stops the camera stream background process.

    Args:
        cam_proc (subprocess.Popen): The camera process to stop.
    """
    if cam_proc:
        try:
            print("🛑 Stopping camera stream...")
            os.killpg(os.getpgid(cam_proc.pid), 9)
        except Exception:
            pass
    return None

def main():
    """Main execution loop for sensor data collection and streaming."""
    global EC_K_VALUE, CAL_POINTS

    # Load persisted calibration values
    load_calibration()

    # 1. Initialize State
    cam_proc = None
    ph_update_mode_active = False

    # Start Camera initially
    cam_proc = start_camera()

    # 2. Initialize Sensors
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)

        # Updated Mapping: Both sensors are on A0
        ec_chan = AnalogIn(ads, 0)
        ph_chan = AnalogIn(ads, 0)
    except Exception as e:
        print(f"Error initializing I2C/ADS1115: {e}")
        if cam_proc:
            stop_camera(cam_proc)
        return

    print("Starting Combined Sensor Monitor & Data Streamer...")
    print("Press 'q' then [Enter] at any time to quit.")
    print(f"FastAPI Endpoint: {FASTAPI_URL}")
    print("-" * 75)
    print(f"{'Temp (°C)':>12} | {'EC (mS/cm)':>12} | {'pH Level':>12} | {'Local Status':>12} | {'Server Status'}")
    print("-" * 75)

    try:
        while True:
            # 0. Check for user quit command
            if check_for_quit():
                print("\n'q' pressed. Stopping...")
                break

            # 1. Check for Active Command
            active_command = get_active_command()

            if active_command and active_command.get("restart_requested"):
                handle_restart(cam_proc)

            bucket_id = active_command.get("active_bucket_id", None) if active_command else None
            experiment_id = active_command.get("active_experiment_id", None) if active_command else None
            ph_update_requested = active_command.get("ph_update_requested", False) if active_command else False
            ec_calibration_requested = active_command.get("ec_calibration_requested", False) if active_command else False
            ph_401_calibration_requested = active_command.get("ph_401_calibration_requested", False) if active_command else False
            ph_686_calibration_requested = active_command.get("ph_686_calibration_requested", False) if active_command else False

            # --- MUTUAL EXCLUSION LOGIC ---
            # If pH update or calibration is requested, we enter "Maintenance Mode"
            # This stops the camera and regular sensor data to focus on precision tasks.
            calibration_active = (
                ph_update_requested or
                ec_calibration_requested or
                ph_401_calibration_requested or
                ph_686_calibration_requested
            )

            if calibration_active and not ph_update_mode_active:
                print("\n🔒 Entering Maintenance Mode: Stopping Camera and Pausing Sensor Logs.")
                cam_proc = stop_camera(cam_proc)
                ph_update_mode_active = True

            # If NO update/calibration is requested, we resume normal operation
            elif not calibration_active and ph_update_mode_active:
                print("\n🔓 Exiting Maintenance Mode: Restarting Camera and Resuming Sensor Logs.")
                cam_proc = start_camera()
                ph_update_mode_active = False

            # 2. Read Temperature
            temp = read_temperature()
            temp_val = temp if temp is not None else 0.0
            temp_str = f"{temp:12.2f}" if temp is not None else f"{'N/A':>12}"

            # 3. Read EC and pH with Sampling (Median Filter)
            ec_readings = []
            ph_readings = []

            # Take 20 samples to filter out noise
            for _ in range(20):
                ec_readings.append(ec_chan.voltage)
                ph_readings.append(ph_chan.voltage)
                time.sleep(0.02)

            # Use median to ignore electrical spikes
            avg_ec_voltage = statistics.median(ec_readings)
            avg_ph_voltage = statistics.median(ph_readings)

            # 4. Calculate Values & Handle Calibration
            if ec_calibration_requested:
                if avg_ec_voltage > 0.1:
                    EC_K_VALUE = 1.413 / avg_ec_voltage
                    print(f" [EC CAL] 💎 Volts: {avg_ec_voltage:.4f}V | New K: {EC_K_VALUE:.4f} | Target: 1.413")
                    save_calibration()
                else:
                    print(f" [EC CAL] ⚠️ Voltage too low for calibration ({avg_ec_voltage:.4f}V)")

            elif ph_401_calibration_requested:
                if avg_ph_voltage > 0.1:
                    # Update pH 4.01 calibration point
                    for i, (v, p) in enumerate(CAL_POINTS):
                        if p == 4.01:
                            CAL_POINTS[i] = (avg_ph_voltage, 4.01)
                            print(f" [pH 4.01 CAL] 🧪 Volts: {avg_ph_voltage:.4f}V | Updated CAL_POINTS | Target: 4.01")
                            save_calibration()
                            break
                else:
                    print(f" [pH 4.01 CAL] ⚠️ Voltage too low for calibration ({avg_ph_voltage:.4f}V)")

            elif ph_686_calibration_requested:
                if avg_ph_voltage > 0.1:
                    # Update pH 6.86 calibration point
                    for i, (v, p) in enumerate(CAL_POINTS):
                        if p == 6.86:
                            CAL_POINTS[i] = (avg_ph_voltage, 6.86)
                            print(f" [pH 6.86 CAL] 🧪 Volts: {avg_ph_voltage:.4f}V | Updated CAL_POINTS | Target: 6.86")
                            save_calibration()
                            break
                else:
                    print(f" [pH 6.86 CAL] ⚠️ Voltage too low for calibration ({avg_ph_voltage:.4f}V)")

            ec_value = avg_ec_voltage * EC_K_VALUE

            # 5. Hybrid Data Strategy & Triggered Update logic
            if ph_update_requested:
                if experiment_id:
                    # Continuous Real-time Mode: Use hardware probe
                    current_ph = get_ph_value(avg_ph_voltage)
                    ph_is_estimated = False
                    local_status = "Real-time"

                    # Send FIFO update to server while session is active
                    UPDATE_URL = f"http://{SERVER_IP}:8000/iot/experiments/{experiment_id}/update-ph"
                    try:
                        up_resp = requests.post(UPDATE_URL, json={"ph": round(current_ph, 2)}, timeout=5.0)
                        if up_resp.status_code == 200:
                            print(f"✅ Continuous Update: {current_ph:.2f}")
                        else:
                            print(f"❌ Continuous Update failed ({up_resp.status_code})")
                    except Exception as e:
                        print(f"❌ Continuous Update Error: {e}")
                else:
                    current_ph = get_ph_value(avg_ph_voltage)
                    ph_is_estimated = False
                    local_status = "Real-time"
                    print("⚠️ pH update active but NO active experiment set on server.")
            else:
                # Standard Hybrid Mode: Use simulated/centralized value
                current_ph = HYBRID_PH_VALUE
                ph_is_estimated = True
                local_status = "Hybrid"

            # 6. Handle Server Communication
            server_status = "Waiting"
            if not active_command:
                server_status = "Offline"
            elif not bucket_id or bucket_id == "STOP":
                server_status = f"Idle ({bucket_id})"
            elif ph_update_requested:
                server_status = "Paused (pH Mode)"
            elif ec_calibration_requested:
                server_status = "EC Calibration"
            elif ph_401_calibration_requested:
                server_status = "pH 4.01 Cal"
            elif ph_686_calibration_requested:
                server_status = "pH 6.86 Cal"
            else:
                # Prepare Minimalist Payload for FastAPI
                payload = {
                    "bucket_id": bucket_id,
                    "temperature": round(temp_val, 2),
                    "ec": round(ec_value, 2),
                    "ph": round(current_ph, 2),
                    "ph_is_estimated": ph_is_estimated
                }

                # Send Data to MacBook FastAPI Server
                try:
                    response = requests.post(FASTAPI_URL, json=payload, timeout=2.0)
                    server_status = f"Sent ({response.status_code})"

                    if response.status_code in [400, 422]:
                        print(f"\n❌ SERVER ERROR ({response.status_code}): {response.text}")
                        print("Check if server schema and leaf_node payload match.")

                except Exception as e:
                    server_status = "Failed"
                    print(f"\n❌ CONNECTION ERROR: {e}")

            # Display Table Row
            status_row = (
                f"{temp_str} | {ec_value:12.2f} | {current_ph:12.2f} | "
                f"{local_status:>12} | {server_status}"
            )
            print(status_row)

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping Monitor and Camera Stream...")
    finally:
        # Cleanup camera process group
        stop_camera(cam_proc)


if __name__ == "__main__":
    main()
