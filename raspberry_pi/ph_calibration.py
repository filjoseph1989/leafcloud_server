import time
import statistics
import json
import os
import requests
from discovery_client import discover_server

# Default pH Calibration points
DEFAULT_CAL_POINTS = [
    (2.508, 6.86),
    (2.931, 4.01)
]

# Mapping sensor names to target pH values
NAME_TO_PH_MAP = {
    "ph_4.01_calibration": 4.01,
    "ph_6.86_calibration": 6.86
}

def get_server_url() -> str:
    """Attempts to discover the server via Zeroconf."""
    print("🔍 Searching for LeafCloud Server...")
    url = discover_server(timeout=10)
    if url:
        return url
    print("⚠️ Discovery failed. Falling back to localhost:8000")
    return "http://localhost:8000"

def get_calibration_states(server_url: str) -> list:
    """Fetches all calibration states from the server."""
    try:
        response = requests.get(f"{server_url}/api/v1/calibration/", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"⚠️ Server connection failed: {e}")
    return []

def reset_calibration_mode(server_url: str, cal_id: int):
    """Tells the server that calibration is finished using its unique ID."""
    try:
        requests.patch(
            f"{server_url}/api/v1/calibration/{cal_id}", 
            json={"is_calibrating": False},
            timeout=5
        )
        print(f"📡 Server state (ID {cal_id}) reset: Calibration Finished.")
    except Exception as e:
        print(f"⚠️ Could not reset server state: {e}")

def get_stable_ph_voltage(ph_channel) -> float:
    ph_readings = []
    for _ in range(20):
        ph_readings.append(ph_channel.voltage)
        time.sleep(0.02)
    return statistics.median(ph_readings)

def update_cal_points(voltage: float, target_ph: float, cal_points: list) -> list:
    if voltage < 0.1:
        return None
    updated_points = []
    point_found = False
    for v, p in cal_points:
        if p == target_ph:
            updated_points.append((voltage, target_ph))
            point_found = True
        else:
            updated_points.append((v, p))
    if not point_found:
        updated_points.append((voltage, target_ph))
    return updated_points

def run_calibration_sequence(server_url: str, cal_id: int, target_ph: float, ph_channel):
    """Performs the hardware reading and saves it."""
    print(f"\n🚀 Signal Received! Starting Hardware Calibration for pH {target_ph}...")
    stable_voltage = get_stable_ph_voltage(ph_channel)
    print(f"📊 Stable Voltage Read: {stable_voltage:.4f}V")
    
    cal_file = "calibration_config.json"
    cal_data = {}
    cal_points = DEFAULT_CAL_POINTS
    if os.path.exists(cal_file):
        try:
            with open(cal_file, 'r') as f:
                cal_data = json.load(f)
                raw_points = cal_data.get("CAL_POINTS", [])
                if raw_points:
                    cal_points = [tuple(p) for p in raw_points]
        except json.JSONDecodeError:
            pass
            
    new_cal_points = update_cal_points(stable_voltage, target_ph, cal_points)
    if new_cal_points:
        print(f"💎 Success! pH {target_ph} -> {stable_voltage:.4f}V")
        cal_data["CAL_POINTS"] = new_cal_points
        with open(cal_file, 'w') as f:
            json.dump(cal_data, f, indent=4)
        print(f"💾 Saved to {cal_file}")
    else:
        print("⚠️ Failed: Voltage too low.")
    
    reset_calibration_mode(server_url, cal_id)

if __name__ == "__main__":
    server_url = get_server_url()
    print(f"📡 Using Server URL: {server_url}")

    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c, address=0x49)
        ph_channel = AnalogIn(ads, 0)
        print("✅ Hardware Ready.")
    except Exception as e:
        print(f"❌ Hardware Error: {e}")
        exit(1)

    print("\n🔄 Entering Continuous Polling Mode...")
    try:
        while True:
            states = get_calibration_states(server_url)
            for item in states:
                name = item.get("sensor_name")
                is_active = item.get("is_calibrating")
                cal_id = item.get("id")
                target_ph = NAME_TO_PH_MAP.get(name)
                
                if is_active and target_ph:
                    run_calibration_sequence(server_url, cal_id, target_ph, ph_channel)
            
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n👋 Polling stopped.")
