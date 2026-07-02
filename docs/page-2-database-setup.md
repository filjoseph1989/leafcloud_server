[Prev](./page-1-login.md) | [Next](./page-3-migrations-alembic.md)

# PostgreSQL Database Setup: `leafcloud3`

This document details the setup and migration from SQLite to **PostgreSQL**.

## 1. What was done?
We transitioned from a file-based database (SQLite) to a more powerful relational database management system (RDBMS), PostgreSQL.

### Changes:
*   Created a new PostgreSQL database named `leafcloud3`.
*   Updated the `.env` file to use the PostgreSQL connection string.
*   Configured the SQLAlchemy engine to support the PostgreSQL driver (`psycopg2`).

---

## 2. Configuration Details

The credentials set in the `.env` file for local development:

*   **DB_USER**: `tin`
*   **DB_PASSWORD**: (none)
*   **DB_HOST**: `localhost`
*   **DB_PORT**: `5432`
*   **DB_NAME**: `leafcloud3`
*   **DATABASE_URL**: `postgresql://tin:@localhost:5432/leafcloud3`

---

## 3. How to Setup the Database

### A. Manual Creation (if needed)
If you need to recreate the database manually:
```bash
psql -U tin -d postgres -c "CREATE DATABASE leafcloud3;"
```

### B. Database Query Utility Script
We added a utility script at `scripts/run-query.sh` to easily execute SQL queries and save results to a file.

**How to use:**
```bash
./scripts/run-query.sh "SELECT * FROM users;"
```
*Results are saved to `database-query.result`.*

To append to results:
```bash
./scripts/run-query.sh --append "SELECT count(*) FROM users;"
```

### C. Database Migrations (Alembic)
Instead of automatic table creation, we now use **Alembic** for more controlled management of the database schema.

**How to run migrations:**
1.  **Check current status**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    ~/.env_leafcloud/bin/alembic current
    ```
2.  **Upgrade to latest version**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    ~/.env_leafcloud/bin/alembic upgrade head
    ```
3.  **Create new migration** (if there are changes in `models.py`):
    ```bash
    export PYTHONPATH=$PYTHONPATH:.
    ~/.env_leafcloud/bin/alembic revision --autogenerate -m "Description of changes"
    ```

### D. Automatic Admin Seeding

1.  **Start the Server**:
    ```bash
    ~/.env_leafcloud/bin/uvicorn app.main:app --reload
    ```
2.  **Check PostgreSQL Tables**:
    You can check if tables were created using `psql`:
    ```bash
    psql -U tin -d leafcloud3 -c "\dt"
    ```
3.  **Test Login**:
    When the server starts, it will still seed the default admin user in PostgreSQL. You can test the login endpoint using `curl` (see `docs/page-1-login.md`).

---

## 5. Why PostgreSQL?
*   **Concurrency**: PostgreSQL is better at handling multiple simultaneous users/requests.
*   **Data Integrity**: PostgreSQL is stricter with types and constraints.
*   **Scalability**: Easier to scale in a production environment (like Cloud SQL or AWS RDS).

---

## 6. Database Backup and Restore

We configured a shell utility to easily perform backups and restores.

### A. Automated Backup Script
Run the automated script in the root directory:
```bash
./scripts/backup-db.sh
```
*   **What it does**: Reads database configurations from `.env` and exports a compressed custom dump file to `exports/leafcloud3_backup_YYYYMMDD_HHMMSS.dump`.

### B. Manual Backup Commands
*   **Custom Compressed Format (Recommended)**:
    ```bash
    pg_dump -h localhost -p 5432 -U tin -F c -b -v -f exports/leafcloud3_backup.dump leafcloud3
    ```
*   **Plain Text SQL Format**:
    ```bash
    pg_dump -h localhost -p 5432 -U tin -F p -v -f exports/leafcloud3_backup.sql leafcloud3
    ```

### C. Restoring from a Backup
*   **For Custom Compressed Format (`.dump`)**:
    1. Recreate the database clean:
       ```bash
       dropdb -h localhost -U tin leafcloud3
       createdb -h localhost -U tin leafcloud3
       ```
    2. Run `pg_restore`:
       ```bash
       pg_restore -h localhost -p 5432 -U tin -d leafcloud3 -v exports/leafcloud3_backup_XXXX.dump
       ```
*   **For Plain SQL Format (`.sql`)**:
    ```bash
    psql -h localhost -U tin -d leafcloud3 -f exports/leafcloud3_backup.sql
    ```

---

[Prev](./page-1-login.md) | [Next](./page-3-migrations-alembic.md)
