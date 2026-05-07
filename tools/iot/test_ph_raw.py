import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import sys
import select

import requests

def check_for_quit():
    """
    Checks if 'q' was pressed on stdin without blocking.
    """
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        key = sys.stdin.read(1)
        if key.lower() == 'q':
            return True
    return False

class BatchCollector:
    """
    Collects sensor readings in memory and prepares batches for transmission.
    """
    def __init__(self, batch_size=10):
        self.batch_size = batch_size
        self.readings = []

    def add_reading(self, raw_adc, voltage, timestamp):
        self.readings.append({
            "timestamp": timestamp,
            "raw_adc": raw_adc,
            "voltage": voltage
        })

    def is_full(self):
        return len(self.readings) >= self.batch_size

    def get_and_clear(self):
        batch = self.readings.copy()
        self.readings = []
        return batch

class NetworkTransmitter:
    """
    Handles transmitting batched data to the server with retry logic.
    """
    def __init__(self, endpoint, device_id="ADS1115_Pi", max_retries=3, base_delay=2.0):
        self.endpoint = endpoint
        self.device_id = device_id
        self.max_retries = max_retries
        self.base_delay = base_delay

    def send_batch(self, batch):
        payload = {
            "device_id": self.device_id,
            "readings": batch
        }

        for attempt in range(self.max_retries):
            try:
                print(f"--- ATTEMPT {attempt + 1}: Transmitting batch to {self.endpoint} ---")
                response = requests.post(self.endpoint, json=payload, timeout=10)

                if response.status_code == 200:
                    print("--- SUCCESS: Batch transmitted successfully ---")
                    return True
                else:
                    print(f"--- FAILURE: Server returned {response.status_code} ---")

            except requests.exceptions.RequestException as e:
                print(f"--- ERROR: Transmission failed: {e} ---")

            # If not the last attempt, wait with exponential backoff
            if attempt < self.max_retries - 1:
                delay = self.base_delay * (2 ** attempt)
                print(f"--- RETRY: Waiting {delay:.1f}s before next attempt... ---")
                time.sleep(delay)

        print("--- FINAL FAILURE: Batch could not be transmitted after maximum retries ---")
        return False

def main():
    try:
        # Initialize I2C and ADS1115
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)

        # pH is typically on A1 (Index 1) based on your leaf_node.py
        # If A1 doesn't move, try changing this to 0, 2, or 3 to test other pins
        ph_chan = AnalogIn(ads, 1)

        print("--- RAW pH SENSOR TEST ---")
        print("Reading from ADS1115 Pin A1...")
        print("Turn the potentiometer and watch for ANY change in voltage.")
        print("Press 'q' then [Enter] or Ctrl+C to stop.")
        print(f"{'Timestamp':>20} | {'Raw ADC':>10} | {'Voltage (V)':>12}")
        print("-" * 50)

        collector = BatchCollector(batch_size=10)
        # Default endpoint for this track as per spec
        transmitter = NetworkTransmitter(endpoint="http://192.168.1.7:8000/iot/logs")

        while True:
            # 0. Check for user quit command
            if check_for_quit():
                print("\n'q' pressed. Stopping...")
                break

            # Get raw values without any filtering
            value = ph_chan.value
            voltage = ph_chan.voltage

            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            print(f"{timestamp:>20} | {value:10d} | {voltage:12.4f}V")

            # Add reading to collector
            collector.add_reading(value, voltage, timestamp)

            # Check if batch is full
            if collector.is_full():
                batch = collector.get_and_clear()
                print(f"--- BATCH READY: {len(batch)} readings captured ---")
                transmitter.send_batch(batch)

            # 0.5s delay so it doesn't scroll too fast to read
            time.sleep(0.5)

    except Exception as e:
        print(f"\nError: {e}")
    except KeyboardInterrupt:
        print("\nTest stopped.")

if __name__ == "__main__":
    main()
