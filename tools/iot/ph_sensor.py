import time
import board
import busio
import json
import sys
import select
import termios
import tty
import statistics
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# 1. Setup I2C and ADC
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
chan = AnalogIn(ads, 0) # Using A0 (Check if physical pin matches)

# 2. Hardcoded Calibration Data (Multi-point Range)
CAL_POINTS = [
    (2.447, 7.00), # Tap Water
    (2.540, 6.86), # pH 6.86 Buffer
    (2.935, 4.01)  # pH 4.01 Buffer
]

def get_ph(voltage):
    # Sort points by voltage to ensure we interpolate correctly
    points = sorted(CAL_POINTS)

    # If voltage is below our lowest point
    if voltage <= points[0][0]:
        v1, p1 = points[0]
        v2, p2 = points[1]
    # If voltage is above our highest point
    elif voltage >= points[-1][0]:
        v1, p1 = points[-2]
        v2, p2 = points[-1]
    else:
        # Find the two points the voltage falls between
        for i in range(len(points) - 1):
            if points[i][0] <= voltage <= points[i+1][0]:
                v1, p1 = points[i]
                v2, p2 = points[i+1]
                break

    # Linear Interpolation formula: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
    slope = (p2 - p1) / (v2 - v1)
    ph_value = p1 + (voltage - v1) * slope
    return round(ph_value, 2)

# 3. Main Loop
print("Reading pH for LEAFCLOUD...")
print("Press 'q' to quit.")

# Save old terminal settings
fd = sys.stdin.fileno()
old_settings = termios.tcgetattr(fd)

try:
    # Set to cbreak mode to read single keypress without Enter
    tty.setcbreak(fd)

    while True:
        # Take 50 readings and use median to remove outliers/spikes
        readings = []
        for _ in range(50):
            readings.append(chan.voltage)
            # Check for 'q' during sampling
            if select.select([sys.stdin], [], [], 0)[0]:
                if sys.stdin.read(1).lower() == 'q':
                    print("\nStopping monitor.")
                    sys.exit(0)
            time.sleep(0.02) # Total sampling time: ~1.0 second

        # Use median filter to ignore electrical noise/spikes
        voltage = statistics.median(readings)
        current_ph = get_ph(voltage)

        # Clear terminal line or print clearly
        print(f"Filtered Voltage: {voltage:.3f}V | Stable pH: {current_ph}")

        # Logic for lettuce health (Target: 5.5 - 6.5)
        if current_ph < 5.5:
            print("ALERT: pH too low (Acidic)!")
        elif current_ph > 6.5:
            print("ALERT: pH too high (Alkaline)!")

        # Wait for a short moment before next batch, checking for 'q'
        start_time = time.time()
        while time.time() - start_time < 0.5:
            if select.select([sys.stdin], [], [], 0)[0]:
                if sys.stdin.read(1).lower() == 'q':
                    print("\nStopping monitor.")
                    sys.exit(0)
            time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping monitor.")
finally:
    # Restore terminal settings
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)