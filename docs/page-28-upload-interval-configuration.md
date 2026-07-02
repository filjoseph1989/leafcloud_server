[Prev](./page-27-camera-streaming.md) | [Next](./page-29-dashboard-code-explanation.md)

# Upload Interval Configuration

This document explains how to configure and control the rate at which your Raspberry Pi uploads sensor readings and plant images to the LeafCloud Server.

## 1. Overview
To prevent flooding the server and bloating the database with telemetry records, you can configure an **upload interval** (in seconds).
*   The **Orchestrator** on the Pi checks the interval before uploading.
*   Once all required sensor values (`ph`, `ec`, `temperature`, and `image_path`) are populated, the Orchestrator enforces a cooldown matching this interval since the last successful upload.
*   During this cooldown, sensors continue reading and updating the local payload, ensuring the *latest* data is uploaded once the cooldown expires.

---

## 2. Configuration Hierarchy (Priority)
The Orchestrator resolves the `upload_interval_seconds` value using the following priority order:

1.  **Server Configuration (Highest Priority)**:
    Queries the database table `tank_configs` via the GET `/api/v1/tank-configs/` endpoint.
    *   If the Pi is assigned to a specific tank via local settings, it fetches that tank's configuration.
    *   Otherwise, it fetches the globally active tank (`is_active = True`).
2.  **Local Override**:
    Reads from the [local_settings.json](../raspberry_pi/local_settings.json) file on the Pi.
3.  **Hardcoded Fallback**:
    Defaults to `60` seconds if the server is offline and no local config is present.

---

## 3. Database Schema (`tank_configs`)
We added the `upload_interval_seconds` column to the `tank_configs` table via an Alembic migration:

| Column | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `upload_interval_seconds` | Integer | `60` | Cooldown period (in seconds) between successful telemetry uploads. |

### SQL representation:
```sql
ALTER TABLE tank_configs ADD COLUMN upload_interval_seconds INTEGER NOT NULL DEFAULT 60;
```

---

## 4. API Endpoints
The upload interval is fully exposed and editable via the FastAPI router endpoints at `/api/v1/tank-configs/`:

*   **List Configurations**: `GET /api/v1/tank-configs/`
*   **Get Configuration**: `GET /api/v1/tank-configs/{config_id}`
*   **Create Configuration**: `POST /api/v1/tank-configs/`
*   **Update Configuration (Mobile/App)**: `PATCH /api/v1/tank-configs/{config_id}`
    *   *Payload example*:
        ```json
        {
            "upload_interval_seconds": 300
        }
        ```

---

## 5. Local Settings File
You can also override this on a specific Pi by editing the local configuration:
**Path**: `raspberry_pi/local_settings.json`
```json
{
    "tank_id": 1,
    "upload_interval_seconds": 120
}
```
