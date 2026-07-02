[Prev](./page-10-npk-predictions.md) | [Next](./page-12-image-processing-logic.md)

# Database Model: **Image Crop Progress**

This document explains the schema and purpose of the `image_crop_progress` table.

## 1. Overview
The `image_crop_progress` table acts as a task tracker and concurrency controller. It manages the status of raw images being processed into segmented crops, ensuring that no image is processed twice and allowing for distributed processing via locking.

## 2. Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `rel_path` | String(255) | Relative path to the raw image file (Unique). |
| `is_processed` | Boolean | Flag indicating if primary cropping is complete. |
| `last_updated` | DateTime (TZ) | Automatically updated whenever the record changes. |
| `locked_until` | DateTime (TZ) | Used for distributed locking; a worker can "claim" an image by setting this to the future. |
| `additional_processed` | Boolean | Flag for secondary or experimental processing passes. |

## 3. Implementation Details
*   **Automatic Timestamps**: Uses `server_default=func.now()` for creation and `onupdate=func.now()` for subsequent changes.
*   **Unique Index**: The `rel_path` is unique to prevent duplicate tracking records for the same physical file.
*   **Distributed Locking**: The `locked_until` field allows multiple scripts or workers to scan for images without colliding.

## 4. Usage Pattern
1.  **Scan**: A script finds a raw image.
2.  **Check/Lock**: It checks if `is_processed` is false AND `locked_until` is in the past.
3.  **Process**: It sets `locked_until` to 10 minutes in the future and begins cropping.
4.  **Complete**: Once done, it sets `is_processed` to true.

## 5. Verification
Check processing status summary:
```bash
./scripts/run-query.sh "SELECT is_processed, count(*) FROM image_crop_progress GROUP BY is_processed;"
```

---

[Prev](./page-10-npk-predictions.md) | [Next](./page-12-image-processing-logic.md)
