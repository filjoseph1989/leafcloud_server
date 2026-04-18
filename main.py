import os
from datetime import datetime, date
from fastapi import FastAPI, Form, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image
from dotenv import load_dotenv
import socket
import anyio
import image_filtering
import shutil
from urllib.parse import urlparse

from database import get_db, engine, Base
import models
from controllers.iot_controller import iot_router, init_iot_controller, resolve_experiment
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import Optional

load_dotenv()

import cv2
import time
import threading

# --- Global State ---
active_bucket_id: Optional[str] = None
active_experiment_id: Optional[str] = None
restart_requested: bool = False
ph_update_requested: bool = False

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
            print(f"📹 Video Manager: Starting for {self.source_url}")

    def stop(self):
        if self.running:
            self.running = False
            print("📹 Video Manager: Stop signal sent.")
            # We don't join with timeout here to avoid blocking the main thread if OpenCV is hung
            # The worker will eventually exit when the timeout hits or next loop starts

    def _is_reachable(self, url: str) -> bool:
        """
        Quickly check if the stream host/port is reachable to avoid OpenCV's 30s hang.
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port
            
            if not host or not port:
                return False

            # Use a short 1s timeout for the reachability check
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (socket.timeout, socket.error, ValueError):
            return False

    def _worker(self):
        while self.running:
            # For UDP listeners (0.0.0.0), we skip the reachability check because 
            # it's a local bind, not a remote connection.
            is_udp_listener = "udp://" in self.source_url and "0.0.0.0" in self.source_url

            if not self.source_url:
                print("⚠️ Video Manager: No source URL provided. Sleeping...")
                time.sleep(5.0)
                continue

            # Only perform reachability check for remote streams (not 0.0.0.0 listeners)
            if not is_udp_listener and not self._is_reachable(self.source_url):
                print(f"⚠️ Video Manager: {self.source_url} not reachable. Retrying in 5s...")
                time.sleep(5.0)
                continue

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

# --- Experiment Models ---
class ExperimentCreate(BaseModel):
    experiment_id: str = Field(..., example="EXP-101")
    bucket_label: Optional[str] = None
    start_date: Optional[date] = None

class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: Optional[str] = None
    bucket_label: Optional[str] = None
    start_date: Optional[date] = None

class ReadingHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    ph: float
    ec: float
    water_temp: float
    image_url: Optional[str] = None
    n: Optional[float] = None
    p: Optional[float] = None
    k: Optional[float] = None

class ExperimentHistoryResponse(BaseModel):
    id: int
    experiment_id: Optional[str] = None
    history: dict[str, list[ReadingHistoryItem]] # Grouped by bucket_label

# --- Auth Models ---
class LoginRequest(BaseModel):
    email: str
    password: str

class ImageInfo(BaseModel):
    filename: str
    reading_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    image_url: str
    is_orphaned: bool = False
    bucket_label: Optional[str] = None


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
    bucket_getter=lambda: active_bucket_id,
    experiment_getter=lambda: active_experiment_id,
    ph_update_getter=lambda: ph_update_requested
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
        "active_experiment_id": active_experiment_id,
        "restart_requested": restart_requested,
        "ph_update_requested": ph_update_requested,
        "server_time": datetime.now().isoformat()
    }

@app.post("/control/request-ph-update")
def request_ph_update():
    """
    Sets the global pH update request flag.
    Called by the Mobile App.
    """
    global ph_update_requested
    ph_update_requested = True
    print("🔔 pH update requested by mobile app. Stopping VideoManager.")
    video_manager.stop()
    return {"status": "success", "ph_update_requested": True}

@app.post("/control/acknowledge-ph-update")
def acknowledge_ph_update():
    """
    Clears the global pH update request flag.
    Called by the IoT device.
    """
    global ph_update_requested
    ph_update_requested = False
    print("✅ pH update acknowledged by IoT device. Flag reset. Restarting VideoManager.")
    video_manager.start()
    return {"status": "success", "ph_update_requested": False}

@app.post("/control/restart-iot")
def restart_iot():
    """
    Sets the global restart flag and restarts the VideoManager.
    Called by the Mobile App.
    """
    global restart_requested
    restart_requested = True
    print("⚠️ Restart requested by mobile app. Resetting VideoManager...")
    video_manager.stop()
    video_manager.start()
    return {"status": "success", "restart_requested": True}

@app.post("/control/acknowledge-restart")
def acknowledge_restart():
    """
    Clears the global restart flag.
    Called by the IoT device.
    """
    global restart_requested
    restart_requested = False
    print("✅ Restart acknowledged by IoT device. Flag reset.")
    return {"status": "success", "restart_requested": False}

class ActiveExperimentRequest(BaseModel):
    experiment_id: Optional[str]

@app.post("/control/active-experiment")
def set_active_experiment(request: ActiveExperimentRequest):
    """
    Updates the global active experiment ID.
    Called by the Mobile App when the user starts a new crop cycle.
    """
    global active_experiment_id
    active_experiment_id = request.experiment_id
    return {"status": "success", "active_experiment_id": active_experiment_id}

@app.post("/control/active-bucket")
def set_active_bucket(request: ActiveBucketRequest, db: Session = Depends(get_db)):
    """
    Updates the global active bucket ID and ensures a corresponding experiment exists.
    """
    global active_bucket_id

    # Log request to file for easier debugging
    with open("control_requests.log", "a") as f:
        f.write(f"{datetime.now()} - Received active bucket request: {request.bucket_id}\n")

    if request.bucket_id == BucketLabel.STOP:
        active_bucket_id = None
        return {
            "status": "success",
            "active_bucket_id": None,
            "message": "System stopped"
        }
    
    # 1. Update in-memory state
    active_bucket_id = request.bucket_id.value

    # 2. Ensure an experiment exists for this bucket (Auto-Initialization)
    experiment = resolve_experiment(db, bucket_label=active_bucket_id)

    return {
        "status": "success",
        "active_bucket_id": active_bucket_id,
        "experiment_id": experiment.experiment_id,
        "message": f"Active bucket set to {active_bucket_id}, linked to experiment {experiment.experiment_id}"
    }

@app.post("/auth/login")
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
    if request.email == "admin@leafcloud.com" and request.password == "admin":
        return {
            "status": "success",
            "token": "demo-access-token-xyz-789",
            "message": "Login successful"
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")

# --- 2. ENDPOINTS FOR EXPERIMENTS ---

@app.post("/experiments/", response_model=ExperimentResponse, status_code=201)
def create_experiment(experiment: ExperimentCreate, db: Session = Depends(get_db)):
    """
    Creates a new experiment.
    """
    db_experiment = db.query(models.Experiment).filter(models.Experiment.experiment_id == experiment.experiment_id).first()
    if db_experiment:
        raise HTTPException(status_code=400, detail="Experiment ID already exists")

    new_exp = models.Experiment(
        experiment_id=experiment.experiment_id,
        bucket_label=experiment.bucket_label,
        start_date=experiment.start_date
    )
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    return new_exp

@app.get("/experiments/", response_model=list[ExperimentResponse])
def list_experiments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Returns a list of all experiments.
    """
    experiments = db.query(models.Experiment).offset(skip).limit(limit).all()
    return experiments

@app.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    """
    Retrieves details of a specific experiment by its internal ID.
    """
    experiment = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment

@app.get("/experiments/{experiment_id}/history", response_model=ExperimentHistoryResponse, response_model_exclude_none=True)
def get_experiment_history(experiment_id: int, db: Session = Depends(get_db)):
    """
    Returns time-series sensor data and AI predictions for a specific experiment, grouped by bucket.
    """
    experiment = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Query with eager loading of prediction
    readings = db.query(models.DailyReading)\
        .filter(models.DailyReading.experiment_id == experiment_id)\
        .order_by(models.DailyReading.timestamp.asc())\
        .all()

    # Group by bucket_label and extract NPK
    # Note: All readings in this query belong to the same experiment, 
    # and thus the same bucket_label from the Experiment table.
    label = experiment.bucket_label or "unknown"
    history_list = []
    
    for r in readings:
        # Manually construct item to handle the nested prediction relationship
        item = {
            "timestamp": r.timestamp,
            "ph": r.ph,
            "ec": r.ec,
            "water_temp": r.water_temp,
            "image_url": f"/images/{os.path.basename(r.image_path)}" if r.image_path else None,
            "n": r.prediction.predicted_n if r.prediction else None,
            "p": r.prediction.predicted_p if r.prediction else None,
            "k": r.prediction.predicted_k if r.prediction else None,
        }
        history_list.append(item)

    return {
        "id": experiment.id,
        "experiment_id": experiment.experiment_id,
        "history": {label: history_list}
    }

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
        "image_url": reading.image_path.replace("\\", "/") if reading.image_path else None,
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
        query = query.join(models.Experiment).filter(models.Experiment.bucket_label == bucket_label)

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

@app.get("/admin/images/", response_model=list[ImageInfo])
def list_images(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Returns a list of images from the images/ directory,
    synced with database metadata from DailyReading.
    """
    image_dir = "images"
    if not os.path.exists(image_dir):
        return []

    # 1. Get all image files from disk
    files = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))], reverse=True)

    # Apply pagination to file list first to avoid massive DB queries
    paginated_files = files[skip : skip + limit]

    # 2. Query DB for these specific files in a single batch
    # We build a list of patterns for the LIKE query, or better, we look for matches
    # since we have the filenames. 
    # NOTE: In production with many files, we might want to store just the filename 
    # in a separate indexed column.
    
    # Fetch all readings that match any of the paginated files
    # We use a join with Experiment to get the bucket_label in one go
    from sqlalchemy.orm import joinedload
    
    # Create a mapping of filename -> reading for quick lookup
    readings_map = {}
    
    # We can optimize the search by looking for image_path that ends with the filename
    # However, for a batch of 50, a simple loop with a slightly better query is okay,
    # but let's try to get as many as possible in one or two queries.
    
    # To keep it simple and robust, we'll fetch all readings that might match
    # and then filter in memory. This is still much faster than N queries.
    if not paginated_files:
        all_matching_readings = []
    elif db.bind.dialect.name == "postgresql":
        all_matching_readings = db.query(models.DailyReading)\
            .options(joinedload(models.DailyReading.experiment))\
            .filter(models.DailyReading.image_path.op('~')('|'.join(paginated_files)))\
            .all()
    else:
        # Fallback for SQLite and others: Batch using multiple OR LIKE conditions
        from sqlalchemy import or_
        filters = [models.DailyReading.image_path.like(f"%{f}%") for f in paginated_files]
        all_matching_readings = db.query(models.DailyReading)\
            .options(joinedload(models.DailyReading.experiment))\
            .filter(or_(*filters))\
            .all()

    for r in all_matching_readings:
        for f in paginated_files:
            if f in r.image_path:
                readings_map[f] = r

    results = []
    for filename in paginated_files:
        reading = readings_map.get(filename)
        if reading:
            results.append(ImageInfo(
                filename=filename,
                reading_id=reading.id,
                timestamp=reading.timestamp,
                image_url=f"/images/{filename}",
                is_orphaned=False,
                bucket_label=reading.experiment.bucket_label if reading.experiment else None
            ))
        else:
            results.append(ImageInfo(
                filename=filename,
                image_url=f"/images/{filename}",
                is_orphaned=True
            ))

    return results

@app.delete("/admin/images/{filename:path}")
def delete_image(
    filename: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Deletes an image from the filesystem and removes its metadata from the DB if present.
    """
    # 1. Authentication Check
    if authorization != "demo-access-token-xyz-789":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Cleanup filename (handle optional 'images/' prefix from URL)
    # If user sends 'images/filename.jpg' or '/images/filename.jpg', we strip it
    clean_filename = filename.lstrip("/").replace("images/", "")

    # 3. Path Traversal Protection & Existence Check
    image_dir = "images"
    if "/" in clean_filename or "\\" in clean_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(image_dir, clean_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Image {clean_filename} not found on disk")

    # 4. Database Cleanup (if record exists)
    # Search for record where image_path contains this filename
    reading = db.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{clean_filename}")).first()

    if reading:
        db.query(models.NPKPrediction).filter(models.NPKPrediction.daily_reading_id == reading.id).delete()
        db.delete(reading)
        db.commit()
        print(f"🗑️ Deleted DB record for reading ID: {reading.id}")

    # 5. Filesystem Deletion
    try:
        os.remove(file_path)
        print(f"🗑️ Deleted file from disk: {file_path}")
    except Exception as e:
        print(f"❌ Failed to delete file: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

    return {"status": "success", "message": f"Image {clean_filename} and associated data deleted"}

class PreFilterRequest(BaseModel):
    size_threshold: int = Field(default=1000, description="Minimum file size in bytes")
    green_threshold: float = Field(default=50.0, description="Minimum greenness percentage")

@app.post("/api/v1/images/pre-filter")
async def pre_filter_images(request: PreFilterRequest, db: Session = Depends(get_db)):
    """
    Triggers the automated pre-filtering process for images.
    - Deletes metadata
    - Deletes corrupted files
    - Moves non-green images to temp_trash
    """
    print(f"📡 API REQUEST: Image Pre-Filtering (size={request.size_threshold}, green={request.green_threshold})")
    
    image_dir = "images"
    trash_dir = os.path.join(image_dir, "temp_trash")
    
    # Run heavy processing in a separate thread to avoid blocking FastAPI
    try:
        stats = await anyio.to_thread.run_sync(
            image_filtering.process_image_batch,
            image_dir,
            trash_dir,
            request.size_threshold,
            request.green_threshold,
            db
        )
        print(f"✅ PRE-FILTER COMPLETE: {stats}")
        return {"status": "success", "stats": stats}
    except Exception as e:
        print(f"❌ PRE-FILTER ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class RestoreRequest(BaseModel):
    log_ids: list[int] = Field(..., description="List of log IDs to restore from trash")

@app.post("/api/v1/images/restore")
async def restore_images(
    request: RestoreRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Restores images from temp_trash to their original location based on log entries.
    """
    # 1. Auth Check
    if authorization != "demo-access-token-xyz-789":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Fetch all requested logs
    logs = db.query(models.AutomatedActionLog).filter(models.AutomatedActionLog.id.in_(request.log_ids)).all()
    
    if len(logs) != len(request.log_ids):
        found_ids = [l.id for l in logs]
        missing_ids = list(set(request.log_ids) - set(found_ids))
        raise HTTPException(status_code=400, detail=f"Some log IDs not found: {missing_ids}")

    # 3. Pre-flight check: Ensure all files exist in current_path
    for log in logs:
        if not os.path.exists(log.current_path):
            raise HTTPException(status_code=400, detail=f"File {log.filename} (ID {log.id}) not found in trash: {log.current_path}")

    # 4. Perform restoration
    restored_count = 0
    try:
        for log in logs:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(log.original_path), exist_ok=True)
            
            # Move file back
            shutil.move(log.current_path, log.original_path)
            
            # Delete log entry
            db.delete(log)
            restored_count += 1
            
        db.commit()
        print(f"♻️ Restored {restored_count} images from trash.")
        return {"status": "success", "message": f"Restored {restored_count} images", "restored_count": restored_count}
        
    except Exception as e:
        db.rollback()
        print(f"❌ RESTORE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restoration failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
