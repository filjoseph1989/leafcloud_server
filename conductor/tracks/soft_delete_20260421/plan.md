# Implementation Plan: Soft-Delete for Images [checkpoint: 6df06a2]

## Phase 1: Update API Endpoint (`DELETE /api/v1/images/{filename}`)
- [x] Task: Update Delete Image Endpoint Tests (6df06a2)
    - [x] Write failing test in `tests/api/` to assert `DELETE /api/v1/images/{filename}` moves the file to `images/temp_trash` with a UUID prefix instead of permanent deletion.
    - [x] Write failing test to assert an `AutomatedActionLog` entry is created with `reason="api_requested_delete"`.
    - [x] Write failing test to assert the associated `DailyReading` is soft-deleted (e.g. `status='deleted'`) and the `NPKPrediction` is NOT deleted.
- [x] Task: Implement Soft-Delete Logic (6df06a2)
    - [x] Update `delete_image` function in `controllers/images_controller.py`.
    - [x] Import `uuid` and `shutil`.
    - [x] Implement file moving to `images/temp_trash/{uuid}_{filename}`.
    - [x] Implement `AutomatedActionLog` creation.
    - [x] Update database logic to set `reading.status = 'deleted'` instead of `db.delete(reading)`.
    - [x] Remove the logic that deletes the associated `NPKPrediction`.
- [x] Task: Refactor and Verify (6df06a2)
    - [x] Ensure all tests pass.
    - [x] Verify test coverage for the modified controller.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Update API Endpoint' (Protocol in workflow.md) (6df06a2)