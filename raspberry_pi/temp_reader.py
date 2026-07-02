import os
import glob
import time
import json
import fcntl
from typing import Optional

# User's known DS18B20 sensor ID (from system configuration)
DEFAULT_SENSOR_ID = "28-0b23581104ae"

class TempReader:
    """
    A class to interface with a DS18B20 1-wire temperature sensor on a Raspberry Pi.
    """
    def __init__(self, sensor_id: str = DEFAULT_SENSOR_ID):
        self.sensor_id = sensor_id
        self.device_file = None

    def initialize_hardware(self) -> bool:
        """
        Initializes and locates the DS18B20 sensor's w1_slave file.
        Falls back to dynamic discovery if the specified sensor ID is not found.
        """
        base_dir = '/sys/bus/w1/devices/'
        
        # 1. Try specified sensor ID first
        target_path = os.path.join(base_dir, self.sensor_id, 'w1_slave')
        if os.path.exists(target_path):
            self.device_file = target_path
            print(f"🌡️ Temperature sensor found with configured ID: {self.sensor_id}")
            return True
            
        # 2. Fallback: Search dynamically for any 28* device
        device_folders = glob.glob(os.path.join(base_dir, '28*'))
        if device_folders:
            discovered_id = os.path.basename(device_folders[0])
            self.device_file = os.path.join(device_folders[0], 'w1_slave')
            print(f"Discovered alternate sensor: {discovered_id}")
            return True

        print("❌ No 1-Wire temperature sensor (DS18B20) detected. Ensure w1-gpio is enabled in /boot/config.txt")
        return False

    def read_temp_raw(self) -> list:
        """Reads raw lines from the 1-wire device interface."""
        if not self.device_file:
            raise RuntimeError("Hardware not initialized. Call initialize_hardware() first.")
        with open(self.device_file, 'r') as f:
            return f.readlines()

    def read_temp(self) -> Optional[float]:
        """
        Reads the temperature from the sensor.
        Performs a CRC check and returns the temperature in Celsius, or None if reading failed.
        """
        try:
            lines = self.read_temp_raw()
            # Wait/retry if CRC check fails (first line does not end with 'YES')
            attempts = 0
            while (not lines or lines[0].strip()[-3:] != 'YES') and attempts < 3:
                time.sleep(0.2)
                lines = self.read_temp_raw()
                attempts += 1
                
            if not lines or lines[0].strip()[-3:] != 'YES':
                print("⚠️ CRC check failed. Temperature reading is invalid.")
                return None
                
            equals_pos = lines[1].find('t=')
            if equals_pos != -1:
                temp_string = lines[1][equals_pos + 2:]
                temp_c = float(temp_string) / 1000.0
                return temp_c
        except Exception as e:
            print(f"❌ Error reading temperature sensor: {e}")
            
        return None

if __name__ == "__main__":
    print("🧪 Starting Temperature Sensor Reader Test...")
    reader = TempReader()
    
    if reader.initialize_hardware():
        print("Reading Temperature. Press Ctrl+C to stop.\n")
        try:
            while True:
                temp_val = reader.read_temp()
                if temp_val is not None:
                    print(f"🌡️ Temperature: {temp_val:.2f} °C")
                    
                    # Safely save the temperature reading in payload.json if "temperature" is not set yet
                    payload_file = "payload.json"
                    try:
                        with open(payload_file, "a+") as f:
                            # Acquire exclusive lock
                            fcntl.flock(f, fcntl.LOCK_EX)
                            
                            f.seek(0)
                            content = f.read()
                            payload = {}
                            if content.strip():
                                try:
                                    payload = json.loads(content)
                                except Exception as e:
                                    print(f"⚠️ Error parsing {payload_file}: {e}")
                                    
                            if "temperature" not in payload:
                                payload["temperature"] = round(temp_val, 2)
                                f.seek(0)
                                f.truncate()
                                json.dump(payload, f, indent=4)
                                print(f"💾 Saved temperature reading {payload['temperature']} to {payload_file}")
                                
                            # Release lock
                            fcntl.flock(f, fcntl.LOCK_UN)
                    except Exception as e:
                        print(f"❌ Failed to safely update {payload_file}: {e}")
                else:
                    print("⚠️ Reading failed.")
                    
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n👋 Exiting Temperature Sensor Reader.")
    else:
        print("\n❌ Could not run test due to hardware initialization failure.")
