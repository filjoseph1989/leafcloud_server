import time
import statistics
import json
import os
import requests
from discovery_client import discover_server

# ==========================================
# CONFIGURATION
# ==========================================
SENSOR_KEY = "ec_calibration"

def get_server_url() -> str:
    """Attempts to discover the server via Zeroconf."""
    print("🔍 Searching for LeafCloud Server...")
    url = discover_server(timeout=10)
    if url:
        return url
    print("⚠️ Discovery failed. Falling back to localhost:8000")
    return "http://localhost:8000"

def get_calibration_record(server_url: str) -> dict:
    """Finds the specific EC calibration record by name."""
    try:
        print(f"📡 Fetching calibration records from server...")
        response = requests.get(f"{server_url}/api/v1/calibration/", timeout=5)
        if response.status_code == 200:
            states = response.json()
            # Find the record where sensor_name matches our key
            for item in states:
                if item.get("sensor_name") == SENSOR_KEY:
                    return item
    except Exception as e:
        print(f"⚠️ Server connection failed: {e}")
    return {}

def reset_calibration_mode(server_url: str, cal_id: int):
    """Tells the server that calibration is finished using its unique ID."""
    try:
        requests.patch(
            f"{server_url}/api/v1/calibration/{cal_id}", 
            json={"is_calibrating": False},
            timeout=5
        )
        print(f"📡 Server state reset (ID {cal_id}): Calibration Finished.")
    except Exception as e:
        print(f"⚠️ Could not reset server state: {e}")

def calculate_ec_k_value(avg_ec_voltage: float, target_ec: float = 1.413) -> float:
    if avg_ec_voltage > 0.1:
        return target_ec / avg_ec_voltage
    return None

def get_stable_ec_voltage(ec_channel) -> float:
    ec_readings = []
    for _ in range(20):
        ec_readings.append(ec_channel.voltage)
        time.sleep(0.02)
    return statistics.median(ec_readings)

def run_ec_calibration(server_url: str, cal_id: int, ec_channel):
    print(f"\n🚀 Signal Received (ID {cal_id})! Starting Hardware Calibration...")
    try:
        print("✅ Reading stable voltage...")
        stable_voltage = get_stable_ec_voltage(ec_channel)
        print(f"📊 Stable Voltage Read: {stable_voltage:.4f}V")
        
        k_value = calculate_ec_k_value(stable_voltage)
        
        if k_value:
            print(f"💎 Success! Your new EC_K_VALUE is: {k_value:.4f}")
            cal_file = "calibration_config.json"
            cal_data = {}
            if os.path.exists(cal_file):
                try:
                    with open(cal_file, 'r') as f:
                        cal_data = json.load(f)
                except json.JSONDecodeError:
                    pass
            cal_data["EC_K_VALUE"] = k_value
            with open(cal_file, 'w') as f:
                json.dump(cal_data, f, indent=4)
            print(f"💾 Successfully saved new K-Value to {cal_file}")
        else:
            print("⚠️ Failed: Voltage too low. Is the probe connected?")
    except Exception as e:
        print(f"❌ Error during hardware calibration: {e}")
    finally:
        reset_calibration_mode(server_url, cal_id)

if __name__ == "__main__":
    server_url = get_server_url()
    print(f"📡 Using Server URL: {server_url}")
    
    ec_channel = None
    try:
        print("🔌 Initializing Hardware on Raspberry Pi...")
        import board
        import busio
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn

        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c, address=0x48)
        ec_channel = AnalogIn(ads, 0)
        print("✅ Hardware initialized successfully.")
    except Exception as e:
        print(f"❌ Hardware Initialization Error: {e}")
        exit(1)

    print(f"\n🔄 Entering Continuous Polling Mode (waiting for '{SENSOR_KEY}' signal)...")
    try:
        while True:
            record = get_calibration_record(server_url)
            if record.get("is_calibrating"):
                active_id = record.get("id")
                run_ec_calibration(server_url, active_id, ec_channel)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n👋 Polling stopped.")
