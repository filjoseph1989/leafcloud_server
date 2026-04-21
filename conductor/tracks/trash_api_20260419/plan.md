# Implementation Plan: Trash Listing API & Images Controller

## Phase 1: Setup and Refactoring
- [ ] Task: Create `controllers/images_controller.py` and define the `images_router`.
- [ ] Task: Migrate Pydantic models related to images (`PreFilterRequest`, `RestoreRequest`, `TrashItemResponse`) to `models.py` or the new controller to ensure availability.
- [ ] Task: Move `POST /api/v1/images/pre-filter` from `main.py` to `controllers/images_controller.py`.
- [ ] Task: Move `POST /api/v1/images/restore` from `main.py` to `controllers/images_controller.py`.
- [ ] Task: Move `DELETE /api/v1/images/{filename:path}` from `main.py` to `controllers/images_controller.py`.
- [ ] Task: Update `main.py` to remove migrated endpoints and include the new `images_router`.
- [ ] Task: Update existing tests (`tests/api/test_pre_filter_api.py`, `tests/api/test_restore_api.py`, `tests/api/test_image_deletion.py`) if needed to ensure they pass with the new routing.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Setup and Refactoring' (Protocol in workflow.md)

## Phase 2: Implement Trash Listing API
- [ ] Task: Write failing test (`tests/api/test_trash_api.py`) for `GET /api/v1/images/trash` (Red Phase).
    - [ ] Write test for successful retrieval of trashed items with pagination (page/size).
    - [ ] Write test for correct sorting (newest first).
    - [ ] Write test for unauthorized access (missing/invalid token).
- [ ] Task: Implement `GET /api/v1/images/trash` in `controllers/images_controller.py` to pass the tests (Green Phase).
    - [ ] Add query to `AutomatedActionLog` filtering by `action_type == 'move_to_trash'`.
    - [ ] Apply `ORDER BY timestamp DESC`.
    - [ ] Apply pagination using `page` and `page_size`.
- [ ] Task: Run tests and verify coverage (>80%).
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Implement Trash Listing API' (Protocol in workflow.md)