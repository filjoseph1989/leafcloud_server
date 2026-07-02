[Prev](./page-22-message-definitions.md) | [Next](./page-23-ec-calibration-math.md)

# Database Model: **Sensor Calibration**

This document explains the schema and purpose of the `sensor_calibrations` table, which tracks the real-time calibration state of the IoT sensors.

## 1. Overview
Calibration is a critical process for pH and EC sensors. During calibration, sensors are placed in buffer solutions that do not represent the actual tank environment. The `sensor_calibrations` table allows the system to flag when a sensor is undergoing maintenance to prevent the server from recording "garbage" data or triggering false alerts.

## 2. Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `sensor_name` | String | The unique name of the sensor (e.g., `ph_sensor`, `ec_sensor`). |
| `is_calibrating` | Boolean | `True` if the sensor is currently being calibrated; `False` otherwise. |
| `updated_at` | DateTime | Timestamp of the last state change. |

## 3. Core Logic & Usage

### Preventing False Readings
The IoT controller (Raspberry Pi) or the Backend API should check the `is_calibrating` flag before:
-   Saving a `daily_reading`.
-   Triggering a `Nutrient Depletion` alert.
-   Running an AI prediction.

If `is_calibrating` is `True`, the system should pause automated actions for that specific sensor to maintain data integrity.

## 4. SQL Verification
To check the current calibration status of all sensors:
```bash
./scripts/run-query.sh "SELECT sensor_name, is_calibrating, updated_at FROM sensor_calibrations;"
```

## 5. Mobile App Integration
The mobile app can use this table to:
1.  **Display a Maintenance Mode UI**: Show a "Calibrating..." spinner or status on the dashboard when the farmer is performing maintenance.
2.  **Safety Lock**: Prevent the farmer from triggering a "Top-up" action if the sensors are not yet ready.


