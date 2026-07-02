[Prev](./page-14-mobile-api-integration.md) | [Next](./page-16-dashboard-api.md)

# IoT Integration: **Raspberry Pi to Server**

This guide explains how your Raspberry Pi can upload sensor data and images to the LeafCloud Server V2.

## 1. Upload Endpoint
**URL**: `http://<server-ip>:8000/api/v1/iot/upload`
**Method**: `POST`
**Content-Type**: `multipart/form-data`

---

## 2. Request Parameters
The Raspberry Pi must send the following fields in a **Multipart** request:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `tank_id` | Integer (Form) | The ID of the Tank/Bucket being monitored. |
| `ph` | Float (Form) | Current pH sensor reading. |
| `ec` | Float (Form) | Current EC sensor reading. |
| `temp` | Float (Form) | Current Water Temperature reading. |
| `image` | File | The JPEG image captured by the Pi Camera. |

---

## 3. Server Workflow
1.  **Instant Response**: The server saves the image and sensor data to the database immediately and returns a "Success" response to the Pi.
2.  **Background Processing**: After responding to the Pi, the server automatically starts the following in the background:
    -   **Auto-Cropping**: Segments the plant image into grids and filters them by greenness.
    -   **AI Prediction**: Runs the multi-modal AI model (Images + Sensors) to estimate nutrient levels.
    -   **Result Storage**: Saves the AI results into the `npk_predictions` table.

---

## 4. Raspberry Pi Example (Python/Requests)

```python
import requests

SERVER_URL = "http://192.168.1.20:8000/api/v1/iot/upload"

def upload_data(image_path, ph, ec, temp, tank_id=1):
    with open(image_path, 'rb') as img_file:
        files = {'image': img_file}
        data = {
            'tank_id': tank_id,
            'ph': ph,
            'ec': ec,
            'temp': temp
        }
        
        try:
            response = requests.post(SERVER_URL, files=files, data=data)
            if response.ok:
                # response contains: {"status": "success", "reading_id": <int>}
                print("Data uploaded successfully:", response.json())
            else:
                print("Upload failed:", response.text)
        except Exception as e:
            print("Connection error:", e)

# Usage
upload_data("plant_snapshot.jpg", 6.5, 1.2, 25.5)
```

## 5. Why use `tank_id`?
By sending a `tank_id`, the Raspberry Pi doesn't need to know anything about "Experiments" or "Bucket Labels." You can change the fertilizer profile or the tank name on the **Mobile Dashboard**, and the server will automatically use those settings for the incoming data from that specific Pi.

---

## 6. Master Orchestrator (Process Manager)
To coordinate all the independent sensor and calibration processes on the Raspberry Pi, we provide a unified master runner: [orchestrator.py](../raspberry_pi/orchestrator.py).

### How to Run:
On your Raspberry Pi, execute the following command:
```bash
python3 raspberry_pi/orchestrator.py
```

### Features:
1.  **Process Management**: Spawns and monitors long-running daemons for `ec_reader.py`, `ph_reader.py`, `temp_reader.py`, `camera_capture.py`, `ec_calibration.py`, and `ph_calibration.py` in separate subprocesses.
2.  **Auto-Respawn**: Checks the health of each process in real-time. If any script crashes or exits unexpectedly, the orchestrator automatically restarts it.
3.  **Unified Console Logging**: Pipes outputs from all processes and prefixes them (e.g. `[EC Reader] ...`, `[Temp Reader] ...`) to make debugging from a single terminal extremely clear.
4.  **Automatic Still Capture**: Spawns `camera_capture.py` as a continuous background daemon that automatically captures a new image when `image_path` is missing from `payload.json`.
5.  **Secure Payload Synchronization & Upload**:
    -   Monitors the locked `payload.json` file.
    -   Once all required sensor values (`ph`, `ec`, `temperature`, and `image_path`) are present, it aggregates them, reads the target image file, and uploads the dataset via multipart/form-data to the server.
    -   **Local Settings Support**: Checks for `local_settings.json` locally on the Pi. If found, it reads the target `tank_id` (enabling multi-Pi/multi-tank deployments).
    -   **Dynamic Active Tank Fallback**: If no local settings file exists, it queries the server's `/api/v1/tank-configs/` endpoint to fetch the currently active tank config (`is_active: True`) and uses its ID dynamically.
    -   Clears only the uploaded keys on success, allowing the cycle to repeat securely.
6.  **Graceful Termination**: Captures `SIGINT` (Ctrl+C) and `SIGTERM` to safely terminate all child processes.


