# Implementation Plan: Automated Image Pre-Filtering (Level 1)

## Phase 1: Core Filtering Logic
- [ ] Task: Create `image_filtering.py` utility module.
    - [ ] Write tests for macOS metadata file identification and deletion.
    - [ ] Implement macOS metadata deletion logic (`._` files).
    - [ ] Write tests for corrupted file identification (size threshold).
    - [ ] Implement corrupted file deletion logic.
    - [ ] Write tests for greenness calculation using OpenCV.
    - [ ] Implement greenness calculation and boolean check against threshold.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Core Filtering Logic' (Protocol in workflow.md)

## Phase 2: Action Engine & Segregation
- [ ] Task: Implement the batch processing engine within `image_filtering.py`.
    - [ ] Write tests to ensure files failing the greenness test are moved to a `temp_trash` directory.
    - [ ] Implement logic to move non-green images to `temp_trash` instead of permanent deletion.
    - [ ] Write tests to ensure metadata and corrupted files are deleted permanently.
    - [ ] Implement permanent deletion for metadata and corrupted captures.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Action Engine & Segregation' (Protocol in workflow.md)

## Phase 3: API Endpoint Integration
- [ ] Task: Add pre-filtering endpoint to the FastAPI application.
    - [ ] Write integration tests for the new endpoint (e.g., POST `/api/v1/images/pre-filter`), verifying parameter passing (size threshold, greenness threshold).
    - [ ] Implement the FastAPI endpoint route, parsing parameters and calling the `image_filtering.py` utility module asynchronously.
    - [ ] Write tests to verify proper error handling and logging (files deleted, moved, processed).
    - [ ] Implement structured logging for the pre-filtering process within the endpoint.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: API Endpoint Integration' (Protocol in workflow.md)