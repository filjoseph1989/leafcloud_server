import os
from datetime import datetime
from fastapi import FastAPI, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image
from dotenv import load_dotenv

from database import get_db, engine, Base
import models
from controllers.iot_controller import iot_router, init_iot_controller
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

load_dotenv()

import cv2
import time
import threading

# --- Global State ---
active_bucket_id: Optional[str] = None

# --- Video Management ---
class VideoManager:
    """
    Manages a single connection to the video stream and shares frames across the app.
    """
    def __init__(self):
        self.source_url = os.getenv("VIDEO_STREAM_URL", "udp://0.0.0.0:5000")
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            print(f"📹 Video Manager started for {self.source_url}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            print("📹 Video Manager stopped.")

    def _worker(self):
        while self.running:
            print(f"📹 Video Manager: Attempting to connect to {self.source_url}")
            cap = cv2.VideoCapture(self.source_url)
            if not cap.isOpened():
                print(f"⚠️ Video Manager: Could not open {self.source_url}. Retrying in 2s...")
                time.sleep(2.0)
                continue

            print(f"✅ Video Manager: Connected to {self.source_url}")
            while self.running:
                success, frame = cap.read()
                if success:
                    with self.lock:
                        self.latest_frame = frame.copy()
                else:
                    print(f"⚠️ Video Manager: Lost stream from {self.source_url}. Reconnecting...")
                    break

            cap.release()
            time.sleep(1.0)

    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
        return None

video_manager = VideoManager()

# --- Models & Enums ---
class BucketLabel(str, Enum):
    NPK = "NPK"
    Micro = "Micro"
    Mix = "Mix"
    Water = "Water"
    STOP = "STOP"

class ActiveBucketRequest(BaseModel):
    bucket_id: BucketLabel

# Ensure tables exist
Base.metadata.create_all(bind=engine)


# --- Auth Models ---
class LoginRequest(BaseModel):
    email: str
    password: str


# Load AI Brain (Mock loader for now if file doesn't exist)
import os
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
try:
    import tensorflow as tf
    model = tf.keras.models.load_model("leafcloud_mobilenetv2_model.h5")
    print("🧠 AI Model loaded successfully.")
except Exception as e:
    print(f"⚠️ AI Model not found or failed to load: {e}. Using dummy predictions.")
    model = None

# Initialize IoT Controller with dependencies
init_iot_controller(
    model=model,
    video_manager=video_manager,
    bucket_getter=lambda: active_bucket_id
)

app = FastAPI(title="LEAFCLOUD API")

# Register Routers
app.include_router(iot_router)

# Serve static images for the app
os.makedirs("images", exist_ok=True)
app.mount("/images", StaticFiles(directory="images"), name="images")

# --- Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    video_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    video_manager.stop()

# --- 1. ENDPOINTS FOR CONTROL ---

@app.get("/control/current-status")
def get_current_status():
    """
    Returns the global active bucket and general system status.
    The Raspberry Pi polls this to know which bucket is active.
    """
    return {
        "active_bucket_id": active_bucket_id,
        "server_time": datetime.now()
    }

@app.post("/control/active-bucket")
def set_active_bucket(request: ActiveBucketRequest):
    """
    Updates the global active bucket ID.
    Called by the Mobile App when the user switches nutrient buckets.

    Args:
        request: An ActiveBucketRequest containing the new bucket_id.

    Returns:
        A dictionary containing the status, updated active_bucket_id, and a message.
    """
    global active_bucket_id

    # Log request to file for easier debugging
    with open("control_requests.log", "a") as f:
        f.write(f"{datetime.now()} - Received active bucket request: {request.bucket_id}\n")

    if request.bucket_id == BucketLabel.STOP:
        active_bucket_id = None
    else:
        active_bucket_id = request.bucket_id.value

    return {
        "status": "success",
        "active_bucket_id": active_bucket_id,
        "message": f"Active bucket set to {active_bucket_id}"
    }

@app.post("/app/login/")
def login(request: LoginRequest):
    """
    Simple authentication endpoint for the mobile app.

    Args:
        request: A LoginRequest containing email and password.

    Returns:
        A dictionary containing status, token, and message if successful.

    Raises:
        HTTPException: If credentials are invalid.
    """
    # In a real app, verify against a Users table with hashed passwords
    if request.email == "admin@leafcloud.com" and request.password == "password":
        return {
            "status": "success",
            "token": "demo-access-token-xyz-789",
            "message": "Login successful"
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")

def generate_recommendation(n, p, k, ph, ec):
    """
    Rule-based engine to convert sensor/AI data into actionable advice.

    Args:
        n: Nitrogen level.
        p: Phosphorus level.
        k: Potassium level.
        ph: pH value.
        ec: EC value.

    Returns:
        A string containing the recommendation.
    """
    # Priority 1: pH Lockout (Critical)
    if ph < 5.5 or ph > 7.0:
        return "pH is out of range. Adjust to 5.8-6.5 immediately. Do not add fertilizer yet."

    # Priority 2: Nutrient Deficiency (Based on AI NPK)
    if n < 100:
        return "Nitrogen levels low. Add Calcium Nitrate to reservoir."
    if p < 30:
        return "Phosphorus levels low. Add Monopotassium Phosphate (MKP)."
    if k < 150:
        return "Potassium levels low. Add Potassium Sulfate."

    # Priority 3: General EC Warning
    if ec < 0.8: # Assuming EC is in mS/cm (800 µS/cm)
        return "Solution is too weak. Add balanced nutrient mix."
    if ec > 2.5: # 2500 µS/cm
        return "Nutrient burn risk. Add fresh water to dilute."

    # Priority 4: Optimal
    return "Lettuce growth is optimal. No action required."

# --- 3. VIDEO STREAMING PROXY ---
@app.get("/video_feed")
async def video_feed():
    """
    Proxies MJPEG stream from the shared VideoManager to the client.
    """
    def generate():
        print(f"📹 Client connected to shared video_feed.")
        frame_count = 0

        while True:
            frame = video_manager.get_latest_frame()

            if frame is None:
                # Fallback: Generate a "NO SIGNAL" placeholder if stream is missing
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, "NO SIGNAL", (220, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(frame, "Waiting for stream...", (10, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                # Encode and yield placeholder
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

                # Sleep briefly to avoid high CPU usage while waiting
                time.sleep(1.0)
            else:
                # Success occasionally log
                if frame_count % 300 == 0:
                    h, w, _ = frame.shape
                    print(f"✅ Serving video frame #{frame_count} ({w}x{h}) from shared VideoManager")
                frame_count += 1

                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    continue

                yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

            # Control frame rate for clients
            time.sleep(0.04) # ~25 FPS

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

# --- 3. ENDPOINT FOR MOBILE APP (Android uses this) ---
@app.get("/app/latest_status/")
def get_dashboard_data(db: Session = Depends(get_db)):
    # The App only ASKS for data (GET), it doesn't send data.
    latest = db.query(models.NPKPrediction)\
        .join(models.DailyReading)\
        .order_by(desc(models.NPKPrediction.prediction_date))\
        .first()

    if not latest:
        return {"error": "No data available yet"}

    # Get the sensor data linked to this prediction
    # Accessing via relationship
    reading = latest.daily_reading

    # Generate actionable advice
    recommendation = generate_recommendation(
        latest.predicted_n,
        latest.predicted_p,
        latest.predicted_k,
        reading.ph,
        reading.ec
    )

    return {
        "timestamp": latest.prediction_date,
        "status": "Optimal" if latest.predicted_n > 100 else "Deficiency Detected",
        "recommendation": recommendation,
        "image_url": reading.image_path.replace("\\", "/") if reading.image_url else None,
        "sensors": {
            "ph": reading.ph,
            "ec": reading.ec,
            "temp": reading.water_temp
        },
        "npk_levels": {
            "Nitrogen": latest.predicted_n,
            "Phosphorus": latest.predicted_p,
            "Potassium": latest.predicted_k
        }
    }

@app.get("/app/history/")
def get_history(limit: int = 30, db: Session = Depends(get_db)):
    """
    Retrieves historical data for charts.
    Returns the last 'limit' readings, ordered chronologically.
    """
    # Join DailyReading (Sensors) with NPKPrediction (AI)
    # We select records that have both sensor data and a prediction
    history = db.query(models.DailyReading, models.NPKPrediction)\
        .join(models.NPKPrediction, models.DailyReading.id == models.NPKPrediction.daily_reading_id)\
        .order_by(models.DailyReading.timestamp.desc())\
        .limit(limit)\
        .all()

    # The query returns a list of tuples: (DailyReading, NPKPrediction)
    # We need to reverse it to be chronological (oldest -> newest) for charts
    history = history[::-1]

    response_data = []
    for reading, prediction in history:
        response_data.append({
            "timestamp": reading.timestamp,
            "ph": reading.ph,
            "ec": reading.ec,
            "temp": reading.water_temp,
            "n_ppm": prediction.predicted_n,
            "p_ppm": prediction.predicted_p,
            "k_ppm": prediction.predicted_k
        })

    return response_data

@app.get("/app/alerts/")
def get_alerts(limit: int = 50, db: Session = Depends(get_db)):
    """
    Retrieves a list of proactive alerts based on historical data.
    Used to populate the 'Notifications' screen in the app.
    """
    # 1. Fetch recent history
    history = db.query(models.DailyReading, models.NPKPrediction)\
        .join(models.NPKPrediction, models.DailyReading.id == models.NPKPrediction.daily_reading_id)\
        .order_by(models.DailyReading.timestamp.desc())\
        .limit(limit)\
        .all()

    alerts = []

    # 2. Scan for issues
    for reading, prediction in history:
        # Check pH (Critical)
        if reading.ph < 5.5 or reading.ph > 7.0:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "critical",
                "message": f"pH Lockout detected ({reading.ph}). Nutrients unavailable."
            })

        # Check EC (Warning)
        if reading.ec < 0.8:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": f"Nutrient solution too weak (EC {reading.ec})."
            })
        elif reading.ec > 2.5:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "critical",
                "message": f"Nutrient burn risk! EC is extremely high ({reading.ec})."
            })

        # Check NPK (Deficiencies)
        if prediction.predicted_n < 100:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": "Nitrogen level is low."
            })
        if prediction.predicted_p < 30:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": "Phosphorus deficiency likely."
            })
        if prediction.predicted_k < 150:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": "Potassium level is below optimal."
            })

    return alerts

@app.get("/admin/readings/")
def list_readings(
    skip: int = 0,
    limit: int = 100,
    bucket_label: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to view raw daily readings.
    Useful for auditing data and verifying sensor inputs.
    """
    query = db.query(models.DailyReading)

    if bucket_label:
        query = query.filter(models.DailyReading.bucket_label == bucket_label)

    # Get total count for pagination UI
    total_count = query.count()

    readings = query.order_by(desc(models.DailyReading.timestamp))\
                    .offset(skip)\
                    .limit(limit)\
                    .all()

    return {
        "total": total_count,
        "page_size": len(readings),
        "readings": readings
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
