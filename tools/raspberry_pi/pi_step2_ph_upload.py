import os 
import time
import json
import statistics
import requests
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# --- CONFIGURATION ---
# Replace with your WSL/Server IP address
SERVER_IP = "192.168.1.5" 
UPLOAD_URL = f"http={SERVER_IP}:8000/upload_data/"

LOCAL_DATA = "pi_temp_data.json"
LOCAL_IMAGE = "pi_temp_image.jpg"
CALIBRATION_FILE = "calibration_config.json"

# Default pH Calibration Points
DEFAULT_PH_POINTS = [
    [2.487, 7.00],  
    [2.931, 4.01]   
]

def load_ph_calibration():
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                points = data.get("PH_POINTS", DEFAULT_PH_POINTS)
                print(f"📂 Loaded pH calibration points from file.")
                return [tuple(p) for p in points]
        except Exception:
            return [tuple(p) for p in DEFAULT_PH_POINTS]
    print(f"ℹ️ Using default pH calibration points.")
    return [tuple(p) for p in DEFAULT_PH_POINTS]

def save_ph_calibration(points):
    try:
        # We need to preserve EC_K_VALUE if it exists
        existing_data = {}
        if os.path.exists(CALIBRATION_FILE):
            with open(CALIBRATION_FILE, 'r') as f:
                existing_data = json.load(f)
        
        existing_data["PH_POINTS"] = points
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(existing_data, f)
        print(f"💾 pH Calibration saved.")
    except Exception as e:
        print(f"❌ Failed to save pH calibration: {e}")

def run_ph_calibration(ph_chan):
    print("\n--- pH CALIBRATION MODE ---")
    print("Buffer Solutions needed: pH 7.0 and pH 4.0")
    choice = input("👉 Start pH calibration? (y/n): ").lower()
    
    if choice != 'y':
        print("⏩ Skipping pH calibration.")
        return None

    # Step A: pH 7.0
    print("\n1️⃣  Dip probe in pH 7.0 buffer.")
    input("Press Enter when stable...")
    readings_7 = []
    for _ in range(50):
        readings_7.append(ph_chan.voltage)
        time.sleep(0.1)
    v_7 = statistics.median(readings_7)
    print(f"✅ Recorded pH 7.0 at {v_7:.4f}V")

    # Step B: pH 4.0
    print("\n2️⃣  Clean probe and dip in pH 4.0 buffer.")
    input("Press Enter when stable...")
    readings_4 = []
    for _ in range(50):
        readings_4.append(ph_chan.voltage)
        time.sleep(0.1)
    v_4 = statistics.median(readings_4)
    print(f"✅ Recorded pH 4.0 at {v_4:.4f}V")

    new_points = [(v_7, 7.00), (v_4, 4.00)]
    save_ph_calibration(new_points)
    return new_points

def get_ph_value(voltage, points):
    """Calculates pH value from voltage using linear interpolation."""
    if voltage < 0.2:
        return -1.0
    sorted_pts = sorted(points)
    if len(sorted_pts) < 2:
        return 7.0
        
    if voltage <= sorted_pts[0][0]:
        v1, p1 = sorted_pts[0]
        v2, p2 = sorted_pts[1]
    elif voltage >= sorted_pts[-1][0]:
        v1, p1 = sorted_pts[-2]
        v2, p2 = sorted_pts[-1]
    else:
        v1, p1, v2, p2 = sorted_pts[0][0], sorted_pts[0][1], sorted_pts[1][0], sorted_pts[1][1]
        for i in range(len(sorted_pts) - 1):
            if sorted_pts[i][0] <= voltage <= sorted_pts[i + 1][0]:
                v1, p1 = sorted_pts[i]
                v2, p2 = sorted_pts[i + 1]
                break
    slope = (p2 - p1) / (v2 - v1)
    ph_value = p1 + (voltage - v1) * slope
    return max(0.0, min(14.0, ph_value))

def main():
    print("🚀 Starting Step 2: pH Reading and Server Upload")

    if not os.path.exists(LOCAL_DATA) or not os.path.exists(LOCAL_IMAGE):
        print("❌ Error: LOCAL DATA or IMAGE NOT FOUND. Did you run Step 1?")
        return

    try:
        # Initialize I2C and ADS1115
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        
        # ASSUMPTION: pH is on Channel 1
        ph_chan = AnalogIn(ads, ADS.P1)

        # 0. Load or Update pH Calibration
        ph_points = load_ph_calibration()
        new_points = run_ph_calibration(ph_chan)
        if new_points:
            ph_points = new_points

        print("\nReading pH...")
        ph_readings = [ph_chan.voltage for _ in range(30)]
        avg_ph_v = statistics.median(ph_readings)
        ph_val = get_ph_value(avg_ph_v, ph_points)
        
        print(f"✅ Active pH Reading: {ph_val:.2f} (Voltage: {avg_ph_v:.4f}V)")

        # Load Step 1 Data
        with open(LOCAL_DATA, 'r') as f:
            step1_data = json.load(f)
        
        print(f"📊 Final Data for Upload: pH={ph_val:.2f}, EC={step1_data['ec']}, Temp={step1_data['temp']}")
        print(f"📤 Uploading to {UPLOAD_URL}...")

        with open(LOCAL_IMAGE, 'rb') as img:
            files = {'image': img}
            payload = {
                'ph': float(ph_val),
                'ec': float(step1_data['ec']),
                'temp': float(step1_data['temp']),
                'bucket_label': 'OPTIMAL' 
            }
            
            response = requests.post(UPLOAD_URL, files=files, data=payload, timeout=10)
            
        if response.status_code == 200:
            print("✅ Data successfully sent to server!")
            # CLEANUP: Delete local files to save space on Pi
            print("🧹 Cleaning up local files...")
            os.remove(LOCAL_DATA)
            os.remove(LOCAL_IMAGE)
            print("✨ Done.")
        else:
            print(f"❌ Server Error ({response.status_code}): {response.text}")

    except Exception as e:
        print(f"❌ Error in Step 2: {e}")

if __name__ == "__main__":
    main()
