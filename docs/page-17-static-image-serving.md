[Prev](./page-16-dashboard-api.md) | [Next](./page-18-history-api.md)

# Static File Serving: **Plant Images**

This document explains how plant images uploaded by the Raspberry Pi are stored and served over HTTP.

## 1. Overview
The server mounts the `images/` directory as a static file endpoint. Any image saved to disk during an IoT upload is immediately accessible via a public URL — no separate file server needed.

## 2. Mount Configuration
Defined in `app/main.py`:
```python
app.mount("/images", StaticFiles(directory=settings.SOURCE_DIR), name="images")
```
`settings.SOURCE_DIR` defaults to `"images"` (relative to the project root).

## 3. Folder Structure
Images are organized by date and tank name, matching the upload endpoint logic:
```
images/
└── {YYYY-MM-DD}/
    └── {tank_name}/
        └── reading_{timestamp}_{uuid}.jpg
```
**Example:**
```
images/2026-05-18/Reservoir/reading_20260518_143022_a3f9c1.jpg
```

## 4. URL Format
```
http://<server-ip>:8000/images/<date>/<tank_name>/<filename>.jpg
```
**Example:**
```
http://192.168.1.20:8000/images/2026-05-18/Reservoir/reading_20260518_143022_a3f9c1.jpg
```

The `image_url` field returned by the dashboard API (`/api/v1/iot/dashboard/{tank_id}`) is already a fully formed URL in this format — the mobile app can use it directly as an image source.

## 5. How the URL is Built
The upload endpoint stores the relative file path in `daily_readings.image_path`. The dashboard endpoint converts it to a full URL at request time:
```python
image_url = str(request.base_url).rstrip("/") + "/" + latest_reading.image_path
```
This means the URL automatically reflects the correct host and port regardless of the deployment environment.

