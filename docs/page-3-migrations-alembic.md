[Prev](./page-2-database-setup.md) | [Next](./page-4-zeroconf-discovery.md)


# Database Migrations: **Alembic**

This document explains how to manage database schema changes using **Alembic**.

## 1. Why use Alembic?
Previously, we used `Base.metadata.create_all()`, but this only creates tables if they don't exist. It cannot handle:
*   Adding new columns to existing tables.
*   Renaming columns.
*   Deleting columns or tables.
*   Tracking the history of database changes.

**Alembic** provides a way for us to track and apply these changes (migrations) in a systematic manner.

---

## 2. Configuration and Setup

### A. Environment Integration
Our Alembic setup is configured to automatically load settings from the `.env` file. See `migrations/env.py`:
```python
load_dotenv()
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))
```
This means Alembic always uses the correct credentials (PostgreSQL on `leafcloud3`).

### B. Model Detection
We also import `Base` from `app.models` so that Alembic can compare the current database schema to our Python models.
```python
from app.models import Base
target_metadata = Base.metadata
```

---

## 3. Standard Workflow (How to use?)

If you change anything in `app/models.py`, follow these steps:

### Step 1: Generate a Migration Script
After changing your models' code, run this command:
```bash
export PYTHONPATH=$PYTHONPATH:.
~/.env_leafcloud/bin/alembic revision --autogenerate -m "Add description here"
```
*This will create a new file in `migrations/versions/` containing Python code for the upgrade and downgrade.*

### Step 2: Review the Migration Script
Open the new file in `migrations/versions/` and ensure the commands (`op.create_table`, `op.add_column`, etc.) are correct.

### Step 3: Apply the Migration
To update the actual database:
```bash
export PYTHONPATH=$PYTHONPATH:.
~/.env_leafcloud/bin/alembic upgrade head
```

---

## 4. Useful Commands (Cheat Sheet)

| Command | Description |
| :--- | :--- |
| `alembic current` | Display the current version of the database. |
| `alembic history` | Display a list of all migrations made. |
| `alembic upgrade head` | Update the database to the latest version. |
| `alembic downgrade -1` | Undo the last migration. |
| `alembic revision --autogenerate` | Automatically detect model changes and create a migration script. |

---

## 5. Reminders (Best Practices)
1.  **Always backup** the database before running `upgrade head` in a production environment.
2.  **Review**: Even with `--autogenerate`, always check the generated script as some complex changes (like renaming) might not be detected correctly.
3.  **PYTHONPATH**: Ensure `PYTHONPATH=.` is set so Alembic can find your `app` module.

---

[Prev](./page-2-database-setup.md) | [Next](./page-4-zeroconf-discovery.md)
