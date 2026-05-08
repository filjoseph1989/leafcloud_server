import os
import time
import json
import statistics
import subprocess
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import glob

# --- CONFIGURATION ---
DEFAULT_K_VALUE = 6.04
CALIBRATION_FILE = "calibration_config.json"
LOCAL_DATA = "pi_temp_data.json"
LOCAL_IMAGE = "pi_temp_image.jpg"

def load_k_value():
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                data = json.load(f)
                val = data.get("EC_K_VALUE", DEFAULT_K_VALUE)
                print(f"📂 Loaded saved K_VALUE from file: {val:.4f}")
                return val
        except Exception:
            return DEFAULT_K_VALUE
    print(f"ℹ️ Using default K_VALUE: {DEFAULT_K_VALUE}")
    return DEFAULT_K_VALUE

def save_k_value(k_value):
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump({"EC_K_VALUE": k_value}, f)
        print(f"💾 Calibration saved: K_VALUE = {k_value:.4f}")
    except Exception as e:
        print(f"❌ Failed to save calibration: {e}")

def run_ec_calibration(ec_chan):
    print("\n--- EC CALIBRATION MODE ---")
    print("Standard Calibration Solution: 1413 µS/cm (1.413 mS/cm)")
    choice = input("👉 Is EC sensor dipped in 1413 µS/cm liquid? (y/n): ").lower()
    
    if choice == 'y':
        print("⏳ Reading stability (5 seconds)...")
        readings = []
        for _ in range(50):
            readings.append(ec_chan.voltage)
            time.sleep(0.1)
        
        avg_v = statistics.median(readings)
        if avg_v < 0.1:
            print("❌ Error: Voltage too low. Check sensor connection.")
            return None
        
        # K = Target_EC / Measured_Voltage
        # Target = 1.413 (mS/cm)
        new_k = 1.413 / avg_v
        print(f"✨ Calibration Done! New K_VALUE: {new_k:.4f} (Voltage: {avg_v:.4f}V)")
        save_k_value(new_k)
        return new_k
    else:
        print("⏩ Skipping calibration.")
        return None

def read_temperature():
    """Reads temperature from DS18B20 1-wire sensor."""
    try:
        device_folders = glob.glob('/sys/bus/w1/devices/28*')
        if not device_folders:
            return 0.0
        device_file = device_folders[0] + '/w1_slave'
        with open(device_file, 'r') as f:
            lines = f.readlines()
        if "YES" in lines[0]: 
            temp_string = lines[1][lines[1].find('t=')+2:]
            return float(temp_string) / 1000.0
    except Exception as e:
        print(f"Temp Error: {e}")
        return 0.0
    return 0.0

def capture_image():
    """Captures an image using rpicam-still."""
    print("📸 Capturing image...")
    try:
        # -t 1000: 1 second delay for auto-white balance
        # --immediate: skip preview
        subprocess.run(["rpicam-still", "-t", "1000", "-o", LOCAL_IMAGE, "--immediate", "--nopreview"], check=True)
        return True
    except Exception as e:
        print(f"❌ Camera Error: {e}")
        return False

def main():
    print("🚀 Starting Step 1: EC, Temperature, and Image Capture")
    
    try:
        # Initialize I2C and ADS1115
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        
        # ASSUMPTION: EC is on Channel 0
        ec_chan = AnalogIn(ads, ADS.P0)

        # 0. Load or Update K_VALUE
        k_value = load_k_value()
        new_k = run_ec_calibration(ec_chan)
        if new_k:
            k_value = new_k
        
        print(f"✅ Active K_VALUE for this session: {k_value:.4f}")

        # 1. Read Sensors
        print("\nReading EC and Temperature...")
        temp = read_temperature()
        
        # Average 30 readings for stability
        ec_readings = [ec_chan.voltage for _ in range(30)]
        avg_ec_v = statistics.median(ec_readings)
        ec_val = avg_ec_v * k_value

        # 2. Capture Image
        if capture_image():
            # 3. Save Data Locally
            data = {
                "ec": round(ec_val, 2),
                "temp": round(temp, 2),
                "timestamp": time.time()
            }

            with open(LOCAL_DATA, 'w') as f:
                json.dump(data, f)
            
            print(f"✅ Step 1 Success!")
            print(f"   - EC: {data['ec']} (K={k_value:.4f})")
            print(f"   - Temp: {data['temp']}")
            print(f"   - Image and Data saved locally. Now run Step 2.")
        else:
            print("❌ Failed to capture image. Aborting.")

    except Exception as e:
        print(f"❌ Error in Step 1: {e}")

if __name__ == "__main__":
    main()
