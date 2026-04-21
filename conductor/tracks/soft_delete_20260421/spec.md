# Specification: Soft-Delete for Images

## Overview
Update the `DELETE /api/v1/images/{filename}` endpoint to move images to a temporary trash directory (`images/temp_trash`) instead of permanently deleting them from the filesystem. This aligns manual deletion via the API with the existing automated `pre-filter` process. Additionally, the associated database records (`DailyReading`) will be soft-deleted instead of permanently removed.

## Functional Requirements
1. **Move File to Trash**: The endpoint must move the specified image file from its current location to `images/temp_trash`.
2. **Unique Filenames**: To prevent collisions in the trash directory, the moved file should have a UUID prefix (e.g., `UUID_filename.jpg`).
3. **Audit Logging**: An entry must be added to the `AutomatedActionLog` table:
   - `action_type`: `move_to_trash`
   - `reason`: `api_requested_delete`
   - `original_path` and `current_path` correctly set.
4. **Database Soft Delete**: The associated `DailyReading` record must be marked as deleted (or soft-deleted). *Note: The `DailyReading` model may need a new `is_deleted` column, or the `status` column can be set to 'deleted'.*

## Non-Functional Requirements
- Ensure database transactions are used so the log entry and soft-delete happen atomically.

## Acceptance Criteria
- Given an existing image and database record, when the DELETE endpoint is called, the file is moved to `images/temp_trash` with a UUID prefix.
- A new log entry in `AutomatedActionLog` exists with the correct paths and the reason `api_requested_delete`.
- The `DailyReading` record is soft-deleted (e.g., `status = 'deleted'`) instead of permanently removed.
- The `NPKPrediction` record associated with the reading is not hard-deleted.

## Out of Scope
- Automatic cleanup of the `temp_trash` directory.
- Restoring the soft-deleted `DailyReading` database record (the `/restore` endpoint currently only restores the physical file).