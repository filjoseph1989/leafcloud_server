# Implementation Plan: Soft-Delete for Images

## Phase 1: Update API Endpoint (`DELETE /api/v1/images/{filename}`)
- [ ] Task: Update Delete Image Endpoint Tests
    - [ ] Write failing test in `tests/api/` to assert `DELETE /api/v1/images/{filename}` moves the file to `images/temp_trash` with a UUID prefix instead of permanent deletion.
    - [ ] Write failing test to assert an `AutomatedActionLog` entry is created with `reason="api_requested_delete"`.
    - [ ] Write failing test to assert the associated `DailyReading` is soft-deleted (e.g. `status='deleted'`) and the `NPKPrediction` is NOT deleted.
- [ ] Task: Implement Soft-Delete Logic
    - [ ] Update `delete_image` function in `controllers/images_controller.py`.
    - [ ] Import `uuid` and `shutil`.
    - [ ] Implement file moving to `images/temp_trash/{uuid}_{filename}`.
    - [ ] Implement `AutomatedActionLog` creation.
    - [ ] Update database logic to set `reading.status = 'deleted'` instead of `db.delete(reading)`.
    - [ ] Remove the logic that deletes the associated `NPKPrediction`.
- [ ] Task: Refactor and Verify
    - [ ] Ensure all tests pass.
    - [ ] Verify test coverage for the modified controller.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Update API Endpoint' (Protocol in workflow.md)