import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import sys
import select

def check_for_quit():
    """
    Checks if 'q' was pressed on stdin without blocking.
    """
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        key = sys.stdin.read(1)
        if key.lower() == 'q':
            return True
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
        print(f"{'Timestamp':>10} | {'Raw ADC':>10} | {'Voltage (V)':>12}")
        print("-" * 40)

        while True:
            # 0. Check for user quit command
            if check_for_quit():
                print("\n'q' pressed. Stopping...")
                break

            # Get raw values without any filtering
            value = ph_chan.value
            voltage = ph_chan.voltage
            
            timestamp = time.strftime("%H:%M:%S")
            print(f"{timestamp:>10} | {value:10d} | {voltage:12.4f}V")
            
            # 0.5s delay so it doesn't scroll too fast to read
            time.sleep(0.5)

    except Exception as e:
        print(f"\nError: {e}")
    except KeyboardInterrupt:
        print("\nTest stopped.")

if __name__ == "__main__":
    main()
