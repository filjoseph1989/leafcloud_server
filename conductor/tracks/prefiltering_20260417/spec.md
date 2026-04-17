# Specification: Automated Image Pre-Filtering (Level 1)

## Overview
Implement an automated pre-filtering system to reduce the volume of plant images requiring human review. The system will clean up macOS metadata, remove corrupted captures, and apply a heuristic "greenness" test to isolate images lacking visible lettuce, moving them to a temporary trash folder for final verification.

## Functional Requirements
- **Trigger Mechanism:** Expose the pre-filtering process as a FastAPI endpoint, allowing it to be triggered remotely.
- **Metadata Cleanup:** Automatically identify and permanently delete macOS `._` hidden files within the target image directories.
- **Corrupted File Removal:** Evaluate file sizes and permanently delete corrupted or "empty" captures falling below a specified byte threshold.
- **Heuristic Filtering (Greenness Test):** Use OpenCV to calculate the percentage of green pixels in each image.
- **Trash Segregation:** Images failing the greenness test (falling below the threshold) must be moved to a `temp_trash` directory instead of being permanently deleted, allowing for manual verification.
- **Configurable Thresholds:** The API endpoint must accept parameters (e.g., query parameters or JSON payload) to configure the minimum file size and the greenness percentage threshold, overriding default values.

## Non-Functional Requirements
- **Performance:** Image processing using OpenCV should be optimized for batch execution without blocking the main asynchronous FastAPI event loop.
- **Safety:** Deletion operations (for metadata and corrupted files) must be strictly scoped to the intended directories to prevent accidental data loss.
- **Logging:** Ensure the number of files deleted, moved, and processed is accurately logged.

## Out of Scope
- Machine learning-based classification (this relies solely on heuristic pixel color analysis).
- Automated emptying of the `temp_trash` directory.