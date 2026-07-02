[Prev](./page-6-daily-readings.md) | [Next](./page-8-experiments.md)

# Database Model: **Cleaned Daily Readings** (Legacy Reference)

This document describes the `cleaned_daily_readings` table, which is now a **legacy/archive** table.

## 1. Overview
The `cleaned_daily_readings` table was originally used to store a processed version of raw sensor data for AI training. As of the IoT pipeline refactor, the `daily_readings` table is now the single source of truth for all sensor data. See `page-6-daily-readings.md` for the current schema.

## 2. Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | BigInteger | Unique identifier (Primary Key). |
| `timestamp` | DateTime (TZ) | The exact date and time the reading was recorded. |
| `image_path` | String | Path to the image associated with this reading. |
| `ph` | Float | The pH level of the water. |
| `ec` | Float | The Electrical Conductivity of the water. |
| `water_temp` | Float | The temperature of the water in Celsius. |
| `experiment_id` | BigInteger | Reference to the experiment this reading belongs to. |
| `tank_id` | Integer | Reference to the tank this reading belongs to. |

## 3. Performance (Indexes)
*   `idx_cleaned_exp_id`: Optimizes lookups for readings belonging to a specific experiment.
*   `idx_cleaned_timestamp`: Optimizes time-series analysis and range-based queries.

## 4. Note
New IoT uploads no longer write to this table. It is retained for historical training data compatibility with `nutrient_classifier.py` scripts that reference older datasets.

---

[Prev](./page-6-daily-readings.md) | [Next](./page-8-experiments.md)
