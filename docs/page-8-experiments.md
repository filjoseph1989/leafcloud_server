[Prev](./page-7-raw-daily-readings.md) | [Next](./page-9-image-crops.md)

# Database Model: **Experiments**

This document explains the schema and purpose of the `experiments` table.

## 1. Overview
The `experiments` table tracks individual hydroponic experiment configurations. It defines the target nutrient ratios and dosages for specific buckets, allowing the AI and analysis scripts to compare actual sensor data against the intended experimental setup.

## 2. Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `bucket_label` | String(50) | Human-readable label (e.g., "NPK", "Water", "Mix"). |
| `start_date` | Date | The date the experiment began. |
| `experiment_id` | String(50) | Unique string identifier for the experiment. |
| `is_current` | Boolean | Flag indicating if the experiment is currently active. |
| `bucket_volume` | Float | The total volume of water in the bucket (in Liters). |
| `n_ratio` | Float | Target Nitrogen ratio. |
| `p_ratio` | Float | Target Phosphorus ratio. |
| `k_ratio` | Float | Target Potassium ratio. |
| `target_dosage` | Float | Target nutrient dosage (e.g., in mL/L). |

## 3. Relationships
The `experiments` table is a parent table for several other entities:
*   **Daily Readings**: Each record in `daily_readings` is linked to an experiment via a foreign key (`experiment_id`).

## 4. Business Logic
- **`is_current`**: This flag is used by the system to automatically filter or prioritize data for the active experimental run.
- **Nutrient Ratios**: The `n_ratio`, `p_ratio`, and `k_ratio` provide the theoretical baseline that the AI models use when attempting to estimate or verify nutrient concentrations.

## 5. Verification
Check all experiments:
```bash
./scripts/run-query.sh "SELECT experiment_id, bucket_label, is_current FROM experiments;"
```

---

[Prev](./page-7-raw-daily-readings.md) | [Next](./page-9-image-crops.md)
