[Prev](./page-23-sensor-calibration.md) | [Next](./page-24-calibration-api.md)

# EC Calibration Math: Understanding the K-Value

This document explains the mathematical formula and logic used for calibrating the EC (Electrical Conductivity) sensor in the Leafcloud system, specifically why we use the formula `target_ec / avg_ec_voltage`.

## 1. The Core Concept: Proportionality (y = mx)
An analog EC sensor essentially measures how well water conducts electricity. 
* If you have pure distilled water (0 mS/cm), it doesn't conduct electricity, so the sensor outputs **~0 Volts**.
* As you add more nutrients/salts, the conductivity increases in a straight, proportional line. 

Because the relationship is a straight line starting at zero, it follows the basic algebra equation for a line: **y = m * x**
* **y** = The actual EC value (mS/cm)
* **x** = The raw voltage read by the sensor
* **m** = The multiplier (which we call the **K-Value**)

## 2. Finding the K-Value (Calibration)
When you calibrate the sensor, you dip it into a standard solution where you already know the exact EC (the **target_ec**, which is usually `1.413`). 

Because you know the target (`y`) and your Raspberry Pi is reading the current voltage (`x`), you just need to solve for the multiplier (`m`):

`m = y / x`

Which translates to the Python code used in `data_gathering.py`:
```python
EC_K_VALUE = 1.413 / avg_ec_voltage
```

**Real World Example:**
Let's say you put the probe in the 1.413 mS/cm solution, and the sensor reads **0.234 Volts**.
* `K = 1.413 / 0.234`
* `K = 6.038`

Now your system knows that to convert *any* voltage into EC, it just needs to multiply by `6.038`.

## 3. Using the K-Value (Normal Reading)
Once calibration is done, normal readings use the reverse of this formula to find the actual EC of the tank:
```python
ec_value = avg_ec_voltage * EC_K_VALUE
```
If a week later the sensor reads **0.300 Volts** in your nutrient tank, the math will be `0.300 * 6.038 = 1.81 mS/cm`.

## 4. Why is this different from pH?
You might notice in the codebase that pH calibration is much more complicated, using multiple points (`CAL_POINTS`) and linear interpolation. 

This is because pH sensors are not perfectly linear and their "zero" point drifts significantly over time and with temperature. Basic EC sensors are much more stable, so a simple **single-point calibration** (just finding that one multiplier) is usually perfectly accurate for hydroponics!
