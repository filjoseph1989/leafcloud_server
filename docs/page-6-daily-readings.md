[Prev](./page-5-developer-guide.md) | [Next](./page-7-raw-daily-readings.md)

# Database Model: **Daily Readings**

This document explains the schema and purpose of the `daily_readings` table.

## 1. Overview
The `daily_readings` table is the **primary storage** for all IoT sensor data uploaded by the Raspberry Pi. Every upload from the Pi creates one row here. The background AI pipeline (cropping + NPK prediction) then links its results back to this table via `image_crops` and `npk_predictions`.

## 2. Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `timestamp` | DateTime (TZ) | Record creation time (Defaults to `now()`). |
| `image_path` | String(255) | Path to the raw image saved on disk. |
| `ph` | Float | pH sensor reading. |
| `ec` | Float | Electrical Conductivity reading. |
| `water_temp` | Float | Water temperature in Celsius. |
| `status` | String(50) | Processing status (`pending`, `processed`). |
| `tank_id` | Integer | FK → `tank_configs.id`. Links the reading to its tank. |
| `experiment_id` | Integer | FK → `experiments.id`. Optional experiment context. |
| `is_new_data` | Boolean | `True` when freshly uploaded; used by the background worker to track unprocessed readings. |

## 3. Relationships
- **Tank Config**: Each reading belongs to one tank, which provides the volume and fertilizer profile used in the dashboard math.
- **Image Crops**: After upload, the background task segments the image and stores each crop in `image_crops`, linked back here via `daily_reading_id`.
- **NPK Predictions**: The AI model's output is stored in `npk_predictions`, also linked via `daily_reading_id`.

## 4. Data Flow
```
Raspberry Pi Upload
      ↓
daily_readings  (status = "pending", is_new_data = True)
      ↓ (background task)
image_crops     (daily_reading_id → daily_readings.id)
npk_predictions (daily_reading_id → daily_readings.id)
```

## 5. Verification
```bash
./scripts/run-query.sh "SELECT id, timestamp, tank_id, status, is_new_data FROM daily_readings ORDER BY timestamp DESC LIMIT 5;"
```

---

[Prev](./page-5-developer-guide.md) | [Next](./page-7-raw-daily-readings.md)
