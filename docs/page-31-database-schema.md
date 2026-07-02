[Prev](./page-30-evaluation.md) | [Next](./page-32-auth-gaps.md)

# LeafCloud Server — Database Schema

## Tables Overview

| Table | Purpose |
|-------|---------|
| `users` | App authentication |
| `tank_configs` | Tank hardware + fertilizer configuration |
| `daily_readings` | Raw IoT uploads from Raspberry Pi |
| `cleaned_daily_readings` | Cleaned/filtered version for AI training |
| `npk_predictions` | AI model output per reading |
| `image_crops` | Cropped images extracted from each reading |
| `experiments` | Labeled experiment buckets used for model training |
| `sensor_calibrations` | Per-sensor calibration state |
| `automated_action_logs` | Audit log of automated file operations |
| `image_crop_progress` | Processing lock/state tracker for crop jobs |

---

## `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `name` | String | |
| `email` | String | Unique, indexed |
| `hashed_password` | String | |

---

## `tank_configs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `tank_name` | String(50) | |
| `water_volume_liters` | Float | Tank capacity in liters |
| `macro_brand_name` | String(100) | |
| `macro_n_pct` | Float | Nitrogen % in macro fertilizer |
| `macro_p_pct` | Float | Phosphorus % |
| `macro_k_pct` | Float | Potassium % |
| `macro_density` | Float | g/mL, default 1.0 |
| `micro_brand_name` | String(100) | |
| `micro_n_pct` | Float | |
| `micro_p_pct` | Float | |
| `micro_k_pct` | Float | |
| `micro_density` | Float | g/mL, default 1.0 |
| `target_macro_dosage_mll` | Float | Target mL of macro per liter of water |
| `target_micro_dosage_mll` | Float | Target mL of micro per liter of water |
| `upload_interval_seconds` | Integer | How often Pi uploads, default 60s |
| `is_active` | Boolean | |
| `created_at` | DateTime (tz) | |
| `updated_at` | DateTime (tz) | Auto-updated |

**Constraints:** `macro_density > 0`, `micro_density > 0`

---

## `daily_readings`

Raw uploads from the Raspberry Pi.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `timestamp` | DateTime (tz) | |
| `image_path` | String(255) | Relative path to raw image |
| `ph` | Float | pH sensor reading |
| `ec` | Float | Electrical conductivity (mS/cm) |
| `water_temp` | Float | Water temperature (°C) |
| `status` | String(50) | `pending`, etc. |
| `tank_id` | Integer | FK → `tank_configs.id` |
| `experiment_id` | Integer | FK → `experiments.id` (nullable) |
| `is_new_data` | Boolean | Flag for unprocessed uploads |

---

## `cleaned_daily_readings`

Cleaned/deduplicated view of readings used for AI model training queries.

| Column | Type | Notes |
|--------|------|-------|
| `id` | BigInteger | PK |
| `timestamp` | DateTime (tz) | |
| `image_path` | String | |
| `ph` | Float | |
| `ec` | Float | |
| `water_temp` | Float | |
| `experiment_id` | BigInteger | |
| `tank_id` | Integer | |

**Indexes:** `experiment_id`, `timestamp`

---

## `npk_predictions`

AI model output linked to each daily reading.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `daily_reading_id` | Integer | FK → `daily_readings.id` |
| `predicted_class` | String | `Water`, `NPK`, `Micro`, `Mix` |
| `is_anomaly` | Boolean | True when classification and regression conflict |
| `macro_scale` | Float | Regression output for macro nutrients (0.0–1.0) |
| `micro_scale` | Float | Regression output for micro nutrients (0.0–1.0) |
| `confidence_score` | Float | Classification confidence (0.0–1.0) |
| `predicted_n` | Float | Legacy: raw clf prob for NPK class |
| `predicted_p` | Float | Legacy: raw clf prob for Micro class |
| `predicted_k` | Float | Legacy: raw clf prob for Mix class |
| `prediction_date` | DateTime (tz) | |

---

## `image_crops`

Cropped sub-images extracted from each raw reading image for AI inference.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `daily_reading_id` | Integer | FK → `daily_readings.id` |
| `crop_path` | String(255) | Path to cropped image file |
| `timestamp` | DateTime (tz) | |
| `crop_type` | String(50) | Default `grid` |

---

## `experiments`

Labeled experiment buckets used for collecting training data.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `experiment_id` | String(50) | Unique identifier, indexed |
| `bucket_label` | String(50) | `Water`, `NPK`, `Micro`, `Mix` |
| `start_date` | Date | |
| `is_current` | Boolean | Marks the active experiment |
| `bucket_volume` | Float | Volume of solution in liters |
| `n_ratio` | Float | Nitrogen ratio in solution |
| `p_ratio` | Float | Phosphorus ratio |
| `k_ratio` | Float | Potassium ratio |
| `target_dosage` | Float | Target dosage in mL/L |

---

## `sensor_calibrations`

Tracks calibration state per sensor.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `sensor_name` | String(100) | Unique, indexed |
| `is_calibrating` | Boolean | True while calibration is in progress |
| `updated_at` | DateTime (tz) | Auto-updated |

---

## `automated_action_logs`

Audit log for automated file management operations.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `filename` | String(255) | |
| `original_path` | String(500) | |
| `current_path` | String(500) | |
| `action_type` | String(100) | e.g. `move`, `delete` |
| `reason` | String(255) | Why the action was taken |
| `metric_value` | Float | e.g. greenness score that triggered action |
| `timestamp` | DateTime (tz) | |

---

## `image_crop_progress`

Processing state tracker to prevent duplicate crop jobs.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | PK |
| `rel_path` | String(255) | Unique relative image path, indexed |
| `is_processed` | Boolean | |
| `last_updated` | DateTime (tz) | Auto-updated |
| `locked_until` | DateTime (tz) | Distributed lock expiry |
| `additional_processed` | Boolean | |

---

## Relationships

```
tank_configs
    └── daily_readings (tank_id)
            ├── npk_predictions (daily_reading_id)
            └── image_crops (daily_reading_id)

experiments
    └── daily_readings (experiment_id)
            └── cleaned_daily_readings (experiment_id)
```
