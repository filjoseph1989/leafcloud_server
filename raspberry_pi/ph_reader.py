import time
import os
import json
import statistics
import fcntl
from typing import Optional

DEFAULT_CAL_POINTS = [
    (2.487, 7.00),
    (2.508, 6.86),
    (2.931, 4.01)
]
CALIBRATION_FILE = "calibration_config.json"

class PHReader:
    """
    A class to interface with the pH sensor via ADS1115 on a Raspberry Pi.
    """
    def __init__(self, channel: int = 0, calibration_file: str = CALIBRATION_FILE):
        self.channel_index = channel
        self.calibration_file = calibration_file
        self.cal_points = self.load_calibration()
        self.ads = None
        self.ph_chan = None

    def load_calibration(self) -> list:
        """Loads CAL_POINTS from the calibration config file, falling back to defaults if unavailable."""
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, 'r') as f:
                    data = json.load(f)
                    raw_points = data.get("CAL_POINTS", [])
                    if raw_points:
                        points = [tuple(p) for p in raw_points]
                        print(f"📂 Loaded CAL_POINTS: {points} from {self.calibration_file}")
                        return points
            except Exception as e:
                print(f"⚠️ Failed to load calibration, using default: {e}")
        return DEFAULT_CAL_POINTS

    def initialize_hardware(self) -> bool:
        """Initializes the I2C bus and ADS1115 analog-to-digital converter."""
        try:
            import board
            import busio
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn

            i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c, address=0x49)
            self.ph_chan = AnalogIn(self.ads, self.channel_index)
            print("🔌 ADS1115 and pH channel initialized successfully.")
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
        if not self.ph_chan:
            raise RuntimeError("Hardware not initialized. Call initialize_hardware() first.")
            
        readings = []
        for _ in range(samples):
            readings.append(self.ph_chan.voltage)
            time.sleep(interval_seconds)
        return statistics.median(readings)

    def calculate_ph_value(self, voltage: float) -> float:
        """
        Translates raw voltage to pH value using multi-point linear interpolation.
        """
        if voltage < 0.2:
            return -1.0 # Invalid/Disconnected sensor signal
            
        points = sorted(self.cal_points)
        
        # Extrapolate if outside calibration ranges
        if voltage <= points[0][0]:
            v1, p1 = points[0]
            v2, p2 = points[1]
        elif voltage >= points[-1][0]:
            v1, p1 = points[-2]
            v2, p2 = points[-1]
        else:
            # Interpolate between the two closest calibration points
            v1, p1 = points[0][0], points[0][1]
            v2, p2 = points[1][0], points[1][1]
            for i in range(len(points) - 1):
                if points[i][0] <= voltage <= points[i + 1][0]:
                    v1, p1 = points[i]
                    v2, p2 = points[i + 1]
                    break
                    
        slope = (p2 - p1) / (v2 - v1)
        ph_value = p1 + (voltage - v1) * slope
        return max(0.0, min(14.0, ph_value))

    def read_ph(self, samples: int = 20) -> float:
        """
        Gathers the median voltage and calculates the pH level.
        """
        voltage = self.read_voltage_median(samples=samples)
        return self.calculate_ph_value(voltage)

if __name__ == "__main__":
    print("🧪 Starting pH Sensor Reader Test...")
    reader = PHReader()
    
    if reader.initialize_hardware():
        print(f"⚙️ Active Calibration Points: {reader.cal_points}")
        print("Reading pH. Press Ctrl+C to stop.\n")
        try:
            while True:
                voltage = reader.read_voltage_median()
                ph_val = reader.read_ph()
                print(f"⚡ Voltage: {voltage:.4f} V | 🧪 Calculated pH: {ph_val:.2f}")
                
                # Safely save the pH reading in payload.json if "ph" is not set yet
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
                                
                        if "ph" not in payload:
                            payload["ph"] = round(ph_val, 2)
                            f.seek(0)
                            f.truncate()
                            json.dump(payload, f, indent=4)
                            print(f"💾 Saved pH reading {payload['ph']} to {payload_file}")
                            
                        # Release lock
                        fcntl.flock(f, fcntl.LOCK_UN)
                except Exception as e:
                    print(f"❌ Failed to safely update {payload_file}: {e}")
                
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n👋 Exiting pH Sensor Reader.")
    else:
        print("\n❌ Could not run test due to hardware initialization failure.")
