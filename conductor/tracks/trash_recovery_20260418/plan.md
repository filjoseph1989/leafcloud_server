# Implementation Plan: Automated Action Log & Trash Recovery System

## Phase 1: Database Migration
- [ ] Task: Add `AutomatedActionLog` class to `models.py` and run migration.
    - [ ] Create the `AutomatedActionLog` model in `models.py`.
    - [ ] Generate Alembic migration script.
    - [ ] Apply the migration to the database.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Database Migration' (Protocol in workflow.md)

## Phase 2: Core Logic Update
- [ ] Task: Update `image_filtering.py` to record logs.
    - [ ] Write/Update tests to verify logging behavior during batch processing (mocking DB session).
    - [ ] Update `process_image_batch` to accept an optional database session and generate log entries.
    - [ ] Ensure `original_path` and `current_path` are correctly determined and stored.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Core Logic Update' (Protocol in workflow.md)

## Phase 3: Recovery API
- [ ] Task: Implement `POST /api/v1/images/restore` endpoint.
    - [ ] Write integration tests for the restore endpoint (testing success, auth failure, and missing file failure).
    - [ ] Implement the FastAPI endpoint in `main.py` with Admin authentication.
    - [ ] Add logic to query logs by ID, move files back to `original_path`, and delete the logs.
    - [ ] Implement error handling for missing files (abort entire request with 400 error).
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Recovery API' (Protocol in workflow.md)

## Phase 4: Pre-Filter Endpoint Update
- [ ] Task: Update `POST /api/v1/images/pre-filter` to pass database session.
    - [ ] Update endpoint logic to pass the `db` session or data back for insertion.
    - [ ] Write/Update integration tests for the updated pre-filter endpoint.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Pre-Filter Endpoint Update' (Protocol in workflow.md)