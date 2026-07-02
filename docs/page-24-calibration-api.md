[Prev](./page-23-ec-calibration-math.md) | [Next](./page-25-how-estimation-works.md)

# API Reference: **Sensor Calibration**

This document details the endpoints used to manage and check the calibration state of IoT sensors.

## 1. Base URL
`http://<server-ip>:8000/api/v1/calibration`

## 2. Endpoints

### A. Get All Calibration States
Returns a list of all sensors and their current calibration status.
- **URL**: `/`
- **Method**: `GET`
- **Response**: `List[SensorCalibration]`

### B. Get Calibration by ID
Retrieve the status of a specific sensor by its unique ID.
- **URL**: `/{id}`
- **Method**: `GET`
- **Response**: `SensorCalibration`

### C. Update Calibration State
Set a sensor to calibration mode (`true`) or normal mode (`false`).
- **URL**: `/{id}`
- **Method**: `PATCH`
- **Body**:
```json
{
  "is_calibrating": true
}
```
- **Response**: `SensorCalibration` (Updated row)

## 3. Sensor IDs (Default)
Based on the initial database seeding:
1. `ec_calibration`
2. `ph_4.01_calibration`
3. `ph_6.86_calibration`

## 4. Usage in IoT Scripts
The Raspberry Pi should poll these endpoints before recording data. If `is_calibrating` is `true` for a specific sensor, the script should skip data upload for that sensor to avoid corrupting the historical records.
