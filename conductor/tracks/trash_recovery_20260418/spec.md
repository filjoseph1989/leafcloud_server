# Specification: Automated Action Log & Trash Recovery System

## Overview
Implement a database-backed tracking system to log automated image filtering actions (e.g., moves to `temp_trash` or permanent deletions). This provides an "Undo" mechanism, allowing administrators to restore images incorrectly flagged by the pre-filtering system.

## Functional Requirements
- **Database Schema:** Create a new `automated_action_logs` table (id, filename, original_path, current_path, action_type, reason, metric_value, timestamp). The `is_restored` flag from the initial plan is omitted as logs will be deleted upon successful restoration.
- **Logging Integration:** Update the `process_image_batch` utility and the `/api/v1/images/pre-filter` endpoint to optionally accept a database session and write a log entry for every image moved to `temp_trash` or permanently deleted.
- **Recovery API:** Implement a new `POST /api/v1/images/restore` endpoint to move files from `temp_trash` back to their `original_path`.
- **API Input:** Accept a list of log IDs for restoration.
- **Restoration Behavior:**
  - If a requested file no longer exists in `temp_trash`, return a 400 error and fail the entire request (no files restored).
  - On successful restoration of a file, its corresponding log entry must be deleted from the database.

## Non-Functional Requirements
- **Security:** The `/api/v1/images/restore` endpoint must require Admin authentication (`authorization` header matching the admin token).
- **Data Integrity:** Database operations for logging and restoration should use transactions to ensure consistency.

## Out of Scope
- Automatic chronological cleanup of old un-restored logs.
- User Interface (UI) for the trash recovery system.