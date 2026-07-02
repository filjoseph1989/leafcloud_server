[Prev](./page-8-experiments.md) | [Next](./page-10-npk-predictions.md)

# Database Model: **Image Crops**

This document explains the schema and purpose of the `image_crops` table.

## 1. Overview
The `image_crops` table stores references to specific segmented or cropped images of plants. These crops are extracted from the raw images referenced in the `daily_readings` table and are used as the primary visual input for the AI training process.

## 2. Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `daily_reading_id` | Integer | Foreign key linking to the parent `daily_readings` record. |
| `crop_path` | String(255) | File system path to the saved image crop. |
| `timestamp` | DateTime (TZ) | Creation time (Defaults to `now()`). |
| `crop_type` | String(50) | Type of crop (Defaults to `grid`). |

## 3. Relationships
- **Daily Reading**: Each crop belongs to a specific daily reading. This relationship links the plant's visual state to the sensor data (pH, EC, etc.) used in the AI training pipeline.

## 4. Role in AI Training
In the `nutrient_classifier.py` script, the `image_crops` table is joined with the `daily_readings` table. The model uses the `crop_path` to load the pixel data and the sensor data from the reading to perform multi-modal classification.

## 5. Verification
List the most recent image crops:
```bash
./scripts/run-query.sh "SELECT crop_path, crop_type, timestamp FROM image_crops ORDER BY timestamp DESC LIMIT 5;"
```

---

[Prev](./page-8-experiments.md) | [Next](./page-10-npk-predictions.md)
