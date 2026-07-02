[Prev](./page-4-zeroconf-discovery.md) | [Next](./page-6-daily-readings.md)

# Developer Guide: LeafCloud Server V2 Architecture

Welcome to the LeafCloud Server V2 codebase. This project has been structured following **SOLID principles** and **FastAPI best practices** to ensure scalability and maintainability.

## 1. Project Structure Overview

The application logic resides in the `app/` directory, organized by layer:

- **`app/core/`**: The "brain" of the application.
  - `config.py`: Environment variable management using `pydantic-settings`.
  - `database.py`: SQLAlchemy engine, session management, and `get_db` dependency.
  - `security.py`: JWT operations and password hashing logic.
- **`app/models/`**: Database definitions.
  - Each file represents a table or a group of related tables (e.g., `user.py`).
- **`app/schemas/`**: Data Transfer Objects (DTOs).
  - Pydantic models for request validation and response serialization.
- **`app/api/v1/`**: Routing layer.
  - `api.py`: The main router that aggregates all endpoints.
  - `endpoints/`: Individual route handlers (controllers), grouped by functionality (e.g., `auth.py`).
- **`app/services/`**: Business logic and external integrations.
  - Use this for complex logic that doesn't belong in a route handler (e.g., `discovery.py` for Zeroconf).
- **`app/main.py`**: Entry point. Handles app initialization, lifespan events, and global router inclusion.

---

## 2. Common Workflows

### How to add a new Feature (e.g., "Devices")

1.  **Define the Model**: Create `app/models/device.py` and add it to `app/models/__init__.py`.
2.  **Create Migrations**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    alembic revision --autogenerate -m "Add device table"
    alembic upgrade head
    ```
3.  **Define Schemas**: Create `app/schemas/device.py` for input/output validation.
4.  **Create Endpoints**: Create `app/api/v1/endpoints/devices.py`.
5.  **Register Router**: Import and include the new router in `app/api/v1/api.py`.

---

## 3. Best Practices & SOLID Principles

-   **Single Responsibility (SRP)**: Keep your route handlers thin. Move complex logic to `app/services/`.
-   **Dependency Inversion**: Use FastAPI's `Depends()` for database sessions or security checks.
-   **Configuration**: Never hardcode values. Add them to `app/core/config.py` and use the `settings` object.
-   **Type Safety**: Always use Python type hints and Pydantic schemas for API inputs and outputs.

---

## 4. Development Tools

-   **Run Server**: `uvicorn app.main:app --reload`
-   **Verify Zeroconf**: `python scripts/verify-zeroconf.py`
-   **Database Queries**: `./scripts/run-query.sh "SELECT * FROM users;"`
-   **Migrations**: Use `alembic` for all schema changes.

## 5. Environment Setup
Always copy `.env.example` to `.env` and configure your local settings before starting development.

---

## 6. Helper Scripts (`scripts/`)

We maintain several utility scripts under the `scripts/` directory to simplify development tasks.

### A. Executing Scripts
To ensure scripts can find the `app` module, we resolved path issues by appending the root directory inside the scripts. You can run them directly from the project root:
```bash
python3 scripts/seed_predictions.py
```

### B. List of Available Scripts
*   **[seed_predictions.py](../scripts/seed_predictions.py)**: Simulates IoT data uploads and generates predictions for testing the UI.
*   **[verify-zeroconf.py](../scripts/verify-zeroconf.py)**: Tests network broadcasting and server discovery.
*   **[run-query.sh](../scripts/run-query.sh)**: Executes PostgreSQL SQL statements directly on `leafcloud3`.
*   **[backup-db.sh](../scripts/backup-db.sh)**: Backs up the database into the `exports/` folder.
*   **[test-alert-trigger.py](../scripts/test-alert-trigger.py)**: Manually sets mock scale prediction inputs and prints the alert endpoint response for testing.

---

[Prev](./page-4-zeroconf-discovery.md) | [Next](./page-6-daily-readings.md)
