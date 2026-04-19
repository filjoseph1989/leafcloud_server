# Specification: Trash Listing API & Images Controller

## 1. Overview
The goal of this track is to introduce a dedicated `images_controller.py` to handle all administrative image actions. This includes refactoring existing endpoints (pre-filter, restore, delete) out of `main.py` and introducing a new `GET /api/v1/images/trash` endpoint. This new endpoint allows the UI to fetch a list of trashed items and their metadata, facilitating user-driven restoration.

## 2. Functional Requirements

### 2.1 Refactoring (`controllers/images_controller.py`)
- Create a new FastAPI router (`APIRouter(prefix="/api/v1/images")`).
- Migrate the following existing logic from `main.py` to the new controller:
  - `POST /pre-filter`
  - `POST /restore`
  - `DELETE /{filename:path}`
- Ensure existing functionality, authorization checks, and database interactions remain intact after migration.

### 2.2 Trash Listing API (`GET /api/v1/images/trash`)
- **Endpoint:** `GET /api/v1/images/trash`
- **Purpose:** Retrieve a list of items currently in the trash (from `AutomatedActionLog` where `action_type = 'move_to_trash'`).
- **Pagination:** Implement pagination using `page` (default 1) and `page_size` (default 50) query parameters.
- **Sorting:** Default ordering is by the `timestamp` column in descending order (Newest items first).
- **Authorization:** Require the administrative token ("demo-access-token-xyz-789") via the `authorization` header, consistent with other administrative image endpoints.

## 3. Non-Functional Requirements
- Maintain test coverage (>80%) for all new and refactored code.
- Ensure the refactoring follows the existing project structure and style guidelines.

## 4. Acceptance Criteria
- [ ] A new file `controllers/images_controller.py` exists and contains the `images_router`.
- [ ] `main.py` no longer contains the implementation for pre-filter, restore, and delete endpoints.
- [ ] `GET /api/v1/images/trash` returns a `200 OK` with a paginated list of trashed items (including `id`, `filename`, `reason`, `metric_value`, and `timestamp`) when authenticated.
- [ ] `GET /api/v1/images/trash` correctly applies `page` and `page_size` for pagination.
- [ ] `GET /api/v1/images/trash` returns items sorted newest first.
- [ ] `GET /api/v1/images/trash` returns `401 Unauthorized` when the correct token is missing.
- [ ] Existing automated tests for pre-filter and restore still pass after refactoring.
- [ ] New unit tests or API tests are added for the `GET /api/v1/images/trash` endpoint.

## 5. Out of Scope
- Modifying the core pre-filtering logic or criteria.
- Adding UI components for the trash bin (this track only covers the backend API).