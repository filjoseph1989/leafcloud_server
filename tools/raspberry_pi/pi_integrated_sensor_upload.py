import os
import time
import json
import statistics
import subprocess
import requests
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import glob
import socket

# --- CONFIGURATION ---
SERVER_IP        = "192.168.1.10"
BASE_URL         = f"http://{SERVER_IP}:8000/iot"
UPLOAD_URL       = f"{BASE_URL}/upload_data/"
EXPERIMENTS_URL  = f"{BASE_URL}/experiments/"
LOCAL_IMAGE      = "pi_temp_image.jpg"
CALIBRATION_FILE = "calibration_config.json"
VALID_LABELS     = ['NPK', 'Micro', 'Mix', 'Water']

DEFAULT_EC_K_VALUE = 6.04
DEFAULT_PH_POINTS = [[2.931, 4.01], [2.500, 6.86]]

def load_calibration():
    ec_k = DEFAULT_EC_K_VALUE
    ph_pts = DEFAULT_PH_POINTS
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                ec_k = data.get("EC_K_VALUE", DEFAULT_EC_K_VALUE)
                ph_pts = data.get("PH_POINTS", DEFAULT_PH_POINTS)
                print(f"📂 Loaded calibration: EC_K={ec_k:.4f}, pH_Points={ph_pts}")
        except Exception as e:
            print(f"⚠️ Error loading calibration: {e}")
    return ec_k, ph_pts

def save_calibration(ec_k, ph_pts):
    try:
        data = {"EC_K_VALUE": ec_k, "PH_POINTS": ph_pts}
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(data, f)
        print(f"💾 Calibration saved to {CALIBRATION_FILE}")
    except Exception as e:
        print(f"❌ Failed to save calibration: {e}")

def get_pi_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def read_temperature():
    try:
        device_folders = glob.glob('/sys/bus/w1/devices/28*')
        if not device_folders: return 0.0
        device_file = device_folders[0] + '/w1_slave'
        with open(device_file, 'r') as f:
            lines = f.readlines()
        if "YES" in lines[0]: 
            temp_string = lines[1][lines[1].find('t=')+2:]
            return float(temp_string) / 1000.0
    except Exception as e:
        print(f"Temp Error: {e}")
    return 0.0

def get_ph_value(voltage, points):
    if voltage < 0.1: return -1.0
    sorted_pts = sorted(points)
    if len(sorted_pts) < 2: return 7.0
    v1, p1 = sorted_pts[0]
    v2, p2 = sorted_pts[1]
    if abs(v2 - v1) < 0.0001: return 7.0
    slope = (p2 - p1) / (v2 - v1)
    ph_value = p1 + (voltage - v1) * slope
    return max(0.0, min(14.0, ph_value))

def get_stable_voltage(channel, samples=30):
    """Takes multiple readings and returns the median (robust average)."""
    readings = []
    for _ in range(samples):
        readings.append(channel.voltage)
        time.sleep(0.1)
    return statistics.median(readings)

def run_ec_calibration(ec_chan, current_k, ph_pts):
    print("\n⚡ --- STEP 1: EC CALIBRATION (OPTIONAL) ---")
    print("Standard Calibration Solution: 1413 µS/cm (1.413 mS/cm)")
    choice = input("👉 Is EC sensor dipped in 1413 µS/cm liquid? (y/n): ").lower()
    if choice == 'y':
        print("⏳ Reading stability (5 seconds)...")
        avg_v = get_stable_voltage(ec_chan, 50)
        if avg_v < 0.1:
            print("❌ Error: Voltage too low. Check sensor connection.")
            return current_k
        new_k = 1.413 / avg_v
        print(f"✨ EC Calibration Done! New K_VALUE: {new_k:.4f}")
        save_calibration(new_k, ph_pts)
        return new_k
    else:
        print("⏩ Skipping EC calibration.")
        return current_k

def main():
    pi_ip = get_pi_ip()
    print("🚀 Starting Integrated Sensor & Upload Script")
    print(f"📡 Pi IP Address: {pi_ip}")

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ec_chan = AnalogIn(ads, 0)
        ph_chan = AnalogIn(ads, 1)
    except Exception as e:
        print(f"❌ Hardware Init Error: {e}")
        return

    while True:
        print("\n" + "═"*60)
        print("🌟 NEW DATA GATHERING SESSION")
        print("═"*60)
        
        ec_k_value, ph_points = load_calibration()

        # --- STEP 1: EC CALIBRATION ---
        ec_k_value = run_ec_calibration(ec_chan, ec_k_value, ph_points)

        # --- STEP 2: NUTSOL EC & TEMP READING ---
        print("\n⚡ --- STEP 2: NUTRIENT SOLUTION EC & TEMP ---")
        input("👉 Clean sensor and dip EC + TEMP sensors in NUTRIENT SOLUTION. Press Enter...")
        print("⏳ Reading EC and Temp stability...")
        temp_val = read_temperature()
        avg_ec_v = get_stable_voltage(ec_chan, 30)
        ec_val = avg_ec_v * ec_k_value
        print(f"✅ EC: {ec_val:.2f} | Temp: {temp_val:.2f}°C")

        # --- STEP 3 & 4: pH CALIBRATION ---
        print("\n🧪 --- STEP 3 & 4: pH CALIBRATION (OPTIONAL) ---")
        if input("👉 Do you want to calibrate pH now? (y/n): ").lower() == 'y':
            input("1️⃣  Dip probe in pH 4.01 buffer. Press Enter...")
            print("⏳ Reading pH 4.01 stability...")
            v_401 = get_stable_voltage(ph_chan, 50)
            
            input("2️⃣  Clean and dip in pH 6.86 buffer. Press Enter...")
            print("⏳ Reading pH 6.86 stability...")
            v_686 = get_stable_voltage(ph_chan, 50)
            
            if abs(v_686 - v_401) < 0.01:
                print("⚠️ Warning: Identical readings. Check sensor.")
            else:
                ph_points = [[v_401, 4.01], [v_686, 6.86]]
                save_calibration(ec_k_value, ph_points)
        else:
            print("⏩ Skipping pH calibration.")

        # --- STEP 5: NUTSOL pH READING ---
        print("\n🧪 --- STEP 5: NUTRIENT SOLUTION pH ---")
        input("👉 Clean sensor and dip pH probe in NUTRIENT SOLUTION. Press Enter...")
        print("⏳ Reading pH stability...")
        avg_ph_v = get_stable_voltage(ph_chan, 30)
        ph_val = get_ph_value(avg_ph_v, ph_points)
        print(f"✅ pH Reading: {ph_val:.2f}")

        # --- STEP 6: CAMERA STAGE ---
        print("\n📸 --- STEP 6: CAMERA STAGE ---")
        try:
            while True:
                subprocess.run(["pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
                if input("👉 Start live stream for positioning? (y/n/skip): ").lower() == 'y':
                    print(f"📡 STREAM STARTING... VLC: tcp://{pi_ip}:5000")
                    proc = subprocess.Popen(
                        ["rpicam-vid", "-t", "0", "--inline", "-g", "30", "--flush", "--listen", "-o", "tcp://0.0.0.0:5000"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    input("👉 PRESS [ENTER] TO STOP STREAM AND CAPTURE PICTURE...")
                    proc.terminate()
                    try: proc.wait(timeout=2)
                    except: proc.kill()
                    subprocess.run(["pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)
                    time.sleep(1)

                print("📸 Capturing still image...")
                subprocess.run(["rpicam-still", "-t", "1000", "-o", LOCAL_IMAGE, "--immediate", "--nopreview"], check=True)
                if input("❓ Is this a good picture? (y/n): ").lower() == 'y': break
                if os.path.exists(LOCAL_IMAGE): os.remove(LOCAL_IMAGE)
        finally:
            subprocess.run(["pkill", "-9", "rpicam-vid"], stderr=subprocess.DEVNULL)

        # --- STEP 6.5: SELECT EXPERIMENT ---
        selected_experiment_id = None
        selected_bucket_label  = None

        print("\n🪣 --- STEP 6.5: SELECT EXPERIMENT ---")
        try:
            res = requests.get(EXPERIMENTS_URL, timeout=10)
            experiments = res.json() if res.status_code == 200 else []
        except Exception as e:
            print(f"⚠️ Could not fetch experiments: {e}")
            experiments = []

        if experiments:
            print("  Available experiments:")
            for i, exp in enumerate(experiments, 1):
                print(f"  {i}. [{exp['bucket_label']}] {exp['experiment_id']} (since {exp['start_date']})")
            print(f"  {len(experiments)+1}. ➕ Create new experiment")
        else:
            print("  No experiments found on server.")
            print(f"  1. ➕ Create new experiment")

        choice = input("👉 Select number: ").strip()

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(experiments):
                # Use existing experiment
                selected_experiment_id = experiments[idx]['experiment_id']
                selected_bucket_label  = experiments[idx]['bucket_label']
                print(f"✅ Selected: [{selected_bucket_label}] {selected_experiment_id}")
            else:
                raise ValueError
        except ValueError:
            # Create new experiment
            print("\n  ➕ New Experiment Setup")
            loc   = input("👉 Location / Farm name (e.g. Farm_A): ").strip().replace(" ", "_")
            print(f"  Bucket label options: {VALID_LABELS}")
            label = input("👉 Bucket label: ").strip()
            if label not in VALID_LABELS:
                print(f"⚠️ Invalid label. Defaulting to 'NPK'.")
                label = 'NPK'
            exp_id = f"EXP-{label.upper()}-{loc.upper()}-{datetime.now().strftime('%Y%m%d')}"
            try:
                r = requests.post(EXPERIMENTS_URL, json={
                    "experiment_id": exp_id,
                    "bucket_label":  label,
                    "location":      loc
                }, timeout=10)
                if r.status_code == 201:
                    selected_experiment_id = exp_id
                    selected_bucket_label  = label
                    print(f"✅ Created: [{label}] {exp_id}")
                else:
                    print(f"❌ Failed to create experiment: {r.text}")
            except Exception as e:
                print(f"❌ Error: {e}")

        # --- STEP 7: FINAL UPLOAD ---
        print(f"\n📤 --- STEP 7: UPLOADING ---")
        print(f"📊 Final Data: pH={ph_val:.2f}, EC={ec_val:.2f}, Temp={temp_val:.2f}")
        print(f"🪣 Experiment: [{selected_bucket_label}] {selected_experiment_id}")
        if input("👉 Ready to upload to server? (y/n): ").lower() == 'y':
            try:
                with open(LOCAL_IMAGE, 'rb') as img:
                    payload = {
                        'ph':            ph_val,
                        'ec':            ec_val,
                        'temp':          temp_val,
                        'bucket_label':  selected_bucket_label or 'Unknown',
                        'experiment_id': selected_experiment_id or '',
                    }
                    res = requests.post(UPLOAD_URL, files={'image': img}, data=payload, timeout=15)
                    if res.status_code == 200:
                        print("🎉 SUCCESS! Data and image sent.")
                        if os.path.exists(LOCAL_IMAGE): os.remove(LOCAL_IMAGE)
                    else:
                        print(f"❌ Error: {res.text}")
            except Exception as e:
                print(f"❌ Failed: {e}")
        else:
            print("🚫 Upload skipped.")

        # --- LOOP CONTROL: QUIT OR CONTINUE ---
        choice = input("\n🔄 Session complete. [Q] to quit, or [ENTER] for another session: ").lower()
        if choice == 'q':
            print("👋 Goodbye!")
            break

if __name__ == "__main__":
    main()
