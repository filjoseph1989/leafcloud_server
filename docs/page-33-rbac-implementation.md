[Prev](./page-32-auth-gaps.md) | [Next](./page-34-token-lifecycle.md)

# Authorization: **Role-Based Access Control (RBAC)**

This document details the Role-Based Access Control (RBAC) security layer implemented in the LeafCloud server. This addresses the vulnerability identified in **[Authentication & Authorization Gaps](./page-32-auth-gaps.md)** (Gap #2: No Role-Based Access Control).

---

## 1. Overview
The authorization layer introduces role differentiation to restrict destructive or administrative actions to administrator accounts, while keeping monitoring, reading, and data-gathering actions accessible to standard authenticated users.

The user role is stored as a boolean flag `is_admin` on the `User` database model:
*   **Standard Users (`is_admin = False`)**: Allowed to register, log in, view telemetry data, read configurations, and poll system alerts.
*   **Administrators (`is_admin = True`)**: Allowed to execute all standard actions, plus add, modify, and delete tank configurations and calibrate hardware sensors.

---

## 2. Access Control Matrix

The table below outlines the access permissions across all API endpoints:

| Endpoint Path | HTTP Method | Required Authentication / Role | Action Description |
| :--- | :---: | :--- | :--- |
| `/api/v1/auth/register` | `POST` | Public / Anonymous | Register new user account (defaults to `is_admin=False`) |
| `/api/v1/auth/login` | `POST` | Public / Anonymous | Authenticate credentials and get JWT access token |
| `/api/v1/iot/upload` | `POST` | Public / Anonymous (IoT Device) | Telemetry upload from Raspberry Pi |
| `/api/v1/tank-configs/` | `GET` | Standard User (`is_admin=False` or `True`) | List all tank configurations |
| `/api/v1/tank-configs/{id}` | `GET` | Standard User (`is_admin=False` or `True`) | Retrieve a specific tank configuration by ID |
| `/api/v1/calibration/` | `GET` | Standard User (`is_admin=False` or `True`) | List all sensor calibrations |
| `/api/v1/calibration/{id}` | `GET` | Standard User (`is_admin=False` or `True`) | Retrieve a specific sensor calibration by ID |
| `/api/v1/iot/dashboard/{id}` | `GET` | Standard User (`is_admin=False` or `True`) | Retrieve the monitoring dashboard for a tank |
| `/api/v1/iot/history/{id}` | `GET` | Standard User (`is_admin=False` or `True`) | Retrieve historical metrics for a tank |
| `/api/v1/iot/alert/{id}` | `GET` | Standard User (`is_admin=False` or `True`) | Retrieve active system alerts |
| `/api/v1/tank-configs/` | `POST` | **Administrator (`is_admin=True`)** | Create a new tank configuration |
| `/api/v1/tank-configs/{id}` | `PATCH` | **Administrator (`is_admin=True`)** | Update an existing tank configuration |
| `/api/v1/tank-configs/{id}` | `DELETE` | **Administrator (`is_admin=True`)** | Delete a tank configuration |
| `/api/v1/calibration/{id}` | `PATCH` | **Administrator (`is_admin=True`)** | Update sensor calibration states |

---

## 3. Database Schema Changes

A new boolean column `is_admin` was added to the `users` table:
*   **Default Value**: `False`
*   **Constraints**: `NOT NULL` (nullable=False), default database server default `'false'`.
*   **SQL Migration**: Generated via Alembic revision `5966fd67cabe` (`add_is_admin_to_user.py`).

```sql
ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT false NOT NULL;
```

---

## 4. Admin Seeding and Auto-Migration

To guarantee administrative privileges on server startup:
1.  **Creation**: The server's startup script checks for the presence of the admin user specified in environment variables (`ADMIN_EMAIL`, `ADMIN_PASSWORD`). If absent, it creates it with `is_admin=True`.
2.  **Auto-Upgrade**: If the admin user already exists but does not have the `is_admin` flag set (e.g. from an older database state before RBAC was implemented), the seeding script dynamically updates the user to `is_admin=True` and commits the changes.

---

## 5. Security Dependencies (FastAPI)

FastAPI dependencies are used to enforce security boundaries across routes.

### Dependency Implementation
In [app/core/security.py](file:///Users/fil/Fil/leafcloud/mimeng_leafcloud_server_v2/app/core/security.py):
```python
def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges"
        )
    return current_user
```

### Dependency Injection in Endpoints
To protect routes, change the injected dependency. For example, in [app/api/v1/endpoints/tank_configs.py](file:///Users/fil/Fil/leafcloud/mimeng_leafcloud_server_v2/app/api/v1/endpoints/tank_configs.py):
```python
@router.post("/", response_model=TankConfigResponse, status_code=status.HTTP_201_CREATED)
def create_tank_config(
    config: TankConfigCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_admin_user)
):
    ...
```

---

## 6. Manual Verification

You can verify authorization rules by executing the verification test script against the FastAPI server context:

```bash
# Run the verification script using the environment python interpreter
/Users/fil/.env_leafcloud_3.11/bin/python3 scripts/verify_rbac.py
```

Expected outputs show that a standard user is blocked with `403 Forbidden` for all writes and deletes, whereas the administrator user executes them successfully.
