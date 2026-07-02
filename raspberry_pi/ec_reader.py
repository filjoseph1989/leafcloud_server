import time
import os
import json
import statistics
import fcntl
from typing import Optional

# Default EC calibration coefficient
DEFAULT_EC_K_VALUE = 6.04
CALIBRATION_FILE = "calibration_config.json"

class ECReader:
    """
    A class to interface with the EC sensor via ADS1115 on a Raspberry Pi.
    """
    def __init__(self, channel: int = 0, calibration_file: str = CALIBRATION_FILE):
        self.channel_index = channel
        self.calibration_file = calibration_file
        self.ec_k_value = self.load_calibration()
        self.ads = None
        self.ec_chan = None

    def load_calibration(self) -> float:
        """Loads EC_K_VALUE from the calibration config file, falling back to default if unavailable."""
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, 'r') as f:
                    data = json.load(f)
                    k_value = data.get("EC_K_VALUE", DEFAULT_EC_K_VALUE)
                    print(f"📂 Loaded EC_K_VALUE: {k_value:.4f} from {self.calibration_file}")
                    return k_value
            except Exception as e:
                print(f"⚠️ Failed to load calibration, using default: {e}")
        return DEFAULT_EC_K_VALUE

    def initialize_hardware(self) -> bool:
        """Initializes the I2C bus and ADS1115 analog-to-digital converter."""
        try:
            import board
            import busio
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn

            i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c, address=0x48)
            self.ec_chan = AnalogIn(self.ads, self.channel_index)
            print("🔌 ADS1115 and EC channel initialized successfully.")
            return True
        except ImportError as e:
            print(f"❌ Python library missing: {e}. Please ensure Adafruit ADS1x15 is installed.")
            return False
        except Exception as e:
            print(f"❌ Failed to initialize I2C/ADS1115 hardware: {e}")
            return False

    def read_voltage_median(self, samples: int = 20, interval_seconds: float = 0.02) -> float:
        """
        Takes multiple voltage readings and returns the median to filter out transient noise.
        """
        if not self.ec_chan:
            raise RuntimeError("Hardware not initialized. Call initialize_hardware() first.")
            
        readings = []
        for _ in range(samples):
            readings.append(self.ec_chan.voltage)
            time.sleep(interval_seconds)
        return statistics.median(readings)

    def read_ec(self, samples: int = 20) -> float:
        """
        Gathers the median voltage and calculates the Electrical Conductivity (EC) value.
        Formula: EC_Value = Voltage * EC_K_VALUE
        """
        voltage = self.read_voltage_median(samples=samples)
        ec_value = voltage * self.ec_k_value
        return ec_value

if __name__ == "__main__":
    print("🧪 Starting EC Sensor Reader Test...")
    reader = ECReader()
    
    if reader.initialize_hardware():
        print(f"⚙️ Active Calibration K-Value: {reader.ec_k_value}")
        print("Reading EC. Press Ctrl+C to stop.\n")
        try:
            while True:
                # Read EC value
                voltage = reader.read_voltage_median()
                ec_val = reader.read_ec()
                print(f"⚡ Voltage: {voltage:.4f} V | 💧 Calculated EC: {ec_val:.2f} mS/cm")
                
                # Safely save the EC reading in payload.json if "ec" is not set yet
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
                                
                        if "ec" not in payload:
                            payload["ec"] = round(ec_val, 2)
                            f.seek(0)
                            f.truncate()
                            json.dump(payload, f, indent=4)
                            print(f"💾 Saved EC reading {payload['ec']} to {payload_file}")
                            
                        # Release lock
                        fcntl.flock(f, fcntl.LOCK_UN)
                except Exception as e:
                    print(f"❌ Failed to safely update {payload_file}: {e}")
                
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n👋 Exiting EC Sensor Reader.")
    else:
        print("\n❌ Could not run test due to hardware initialization failure.")
