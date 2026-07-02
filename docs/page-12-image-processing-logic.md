[Prev](./page-11-image-crop-progress.md) | [Next](./page-13-tank-configuration.md)

# Image Processing Logic: `image_processor.py`

This document explains how the raw images are segmented and filtered before being used by the AI.

## 1. Overview
The `image_processor.py` script is responsible for transforming large raw plant photos into small, high-quality segments (crops) that the deep learning model can ingest. It follows the **Single Responsibility Principle (SRP)** by delegating low-level tasks to the `app/services/image_processing.py` module.

## 2. Core Workflow
1.  **Cleanup**: Removes macOS-specific metadata files (`._`) from the source directory.
2.  **Discovery**: Scans the `images/` directory for new files.
3.  **Progress Tracking**: Checks the `image_crop_progress` table to see if the image was already processed.
4.  **Segmentation**: Applies multiple cropping strategies (Grid, Edges, Corners, Random).
5.  **Filtering**: Calculates the **Greenness Percentage** for each crop. If a crop has less than 30% green pixels (mostly water or background), it is discarded.
6.  **Database Integration**: Links the valid crops to their corresponding `daily_readings`.

---

## 3. Cropping Strategies
To maximize the dataset variety, we use five different coordinate generation methods:
-   **Grid**: Standard non-overlapping tiles.
-   **Right Aligned**: Ensures the right edge of the plant is captured.
-   **Bottom Aligned**: Ensures the bottom edge is captured.
-   **Corner**: Specifically targets the bottom-right corner.
-   **Random**: Adds 3 stochastic samples to prevent the model from memorizing specific grid positions.

---

## 4. Greenness Filtering
We use the **HSV (Hue, Saturation, Value)** color space to identify plant material.
-   **Green Hue Range**: 35 to 85.
-   **Threshold**: 30.0%
-   **Trash logic**: Crops that fail this check are moved to a `temp_trash` folder and logged in the `automated_action_logs` table for audit.

---

## 5. How to Run
Ensure your environment variables for `SOURCE_DIR` and `OUTPUT_DIR` are set in `.env`, then run:
```bash
export PYTHONPATH=$PYTHONPATH:.
python scripts/image_processor.py
```

## 6. Associated Table: `automated_action_logs`
This table tracks every time a crop is discarded.
-   `metric_value`: Stores the actual greenness percentage calculated.
-   `reason`: Typically `low_greenness_crop`.

---

[Prev](./page-11-image-crop-progress.md) | [Next](./page-13-tank-configuration.md)
