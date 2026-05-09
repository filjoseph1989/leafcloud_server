import os
import shutil
import cv2
import random
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image
from typing import List

from database import get_db
import models
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


# The router for all IoT-related endpoints
iot_router = APIRouter(prefix="/iot", tags=["IoT"])

# Configuration for auto-cropping
CROP_SIZE = 224
GREEN_THRESHOLD = 30.0 # Minimum 30% green to be considered a leaf

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        
        # Mutual Exclusion: Stop camera if this is the first pH stream client
        if len(self.active_connections) == 0:
            if VIDEO_MANAGER:
                print("🔒 pH Stream Active: Stopping Video Manager to prioritize resources.")
                VIDEO_MANAGER.stop()
        
        self.active_connections.append(websocket)
        print(f"🔌 New WS connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"🔌 WS disconnected. Total: {len(self.active_connections)}")
            
            # Mutual Exclusion: Restart camera if NO MORE pH stream clients
            # BUT only if pH update is no longer requested globally.
            if len(self.active_connections) == 0:
                if is_ph_update_requested():
                    print("🔒 pH Update STILL Requested globally. Keeping Video Manager stopped.")
                elif VIDEO_MANAGER:
                    print("🔓 pH Stream Inactive: Restarting Video Manager.")
                    VIDEO_MANAGER.start()

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"⚠️ Failed to send WS message: {e}")
                # Optional: handle stale connections here

manager = ConnectionManager()

# Internal references that will be injected or accessed globally
AI_MODEL = None
VIDEO_MANAGER = None
ACTIVE_BUCKET_GETTER = None
ACTIVE_EXPERIMENT_GETTER = None
PH_UPDATE_REQUESTED_GETTER = None

def init_iot_controller(model=None, video_manager=None, bucket_getter=None, experiment_getter=None, ph_update_getter=None):
    """Initializes the controller with necessary global state."""
    global AI_MODEL, VIDEO_MANAGER, ACTIVE_BUCKET_GETTER, ACTIVE_EXPERIMENT_GETTER, PH_UPDATE_REQUESTED_GETTER
    AI_MODEL = model
    VIDEO_MANAGER = video_manager
    ACTIVE_BUCKET_GETTER = bucket_getter
    ACTIVE_EXPERIMENT_GETTER = experiment_getter
    PH_UPDATE_REQUESTED_GETTER = ph_update_getter

SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 10.0),
    'water_temp': (15.0, 35.0),
}

def _normalize_sensors(reading) -> np.ndarray:
    def norm(val, lo, hi):
        return float(np.clip((val - lo) / (hi - lo), 0.0, 1.0))
    return np.array([[
        norm(reading.ph,         *SENSOR_NORM['ph']),
        norm(reading.ec,         *SENSOR_NORM['ec']),
        norm(reading.water_temp, *SENSOR_NORM['water_temp']),
    ]], dtype=np.float32)

def _is_green_array(crop_bgr) -> bool:
    """Greenness check directly on a BGR numpy array — no temp file needed."""
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    lower_green = np.array([35, 50, 60])
    upper_green = np.array([85, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    total = crop_bgr.shape[0] * crop_bgr.shape[1]
    return (cv2.countNonZero(mask) / total * 100.0) >= GREEN_THRESHOLD if total else False


def _get_all_crop_coords(w: int, h: int, size: int):
    """Returns (x, y) coords for grid + right-edge + bottom-edge + corner + 3 random crops."""
    coords = []
    for y in range(0, h - size + 1, size):
        for x in range(0, w - size + 1, size):
            coords.append((x, y))
    if w > size:
        for y in range(0, h - size + 1, size):
            coords.append((w - size, y))
    if h > size:
        for x in range(0, w - size + 1, size):
            coords.append((x, h - size))
    if w > size and h > size:
        coords.append((w - size, h - size))
    for _ in range(3):
        coords.append((random.randint(0, w - size), random.randint(0, h - size)))
    return coords


def _predict_from_arrays(crop_arrays: list, reading, db: Session) -> bool:
    """Run AI prediction on in-memory crop arrays. No file I/O, no DB crop records."""
    if not AI_MODEL or not crop_arrays:
        return False

    is_multimodal = len(AI_MODEL.inputs) > 1
    sensor_array = _normalize_sensors(reading) if (is_multimodal and reading) else None

    crop_preds = []
    for crop_bgr in crop_arrays:
        try:
            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            img_array = np.expand_dims(cv2.resize(crop_rgb, (224, 224)) / 255.0, axis=0)
            if is_multimodal and sensor_array is not None:
                pred = AI_MODEL.predict([img_array, sensor_array], verbose=0)
            else:
                pred = AI_MODEL.predict(img_array, verbose=0)
            crop_preds.append(pred[0])
        except Exception as e:
            print(f"⚠️ _predict_from_arrays: crop error: {e}")

    if not crop_preds:
        return False

    avg = np.mean(crop_preds, axis=0)
    npk_ml_l, micro_ml_l = avg
    predicted_n = max(0.0, (npk_ml_l * 80.0) + (micro_ml_l * 80.0))
    predicted_p = max(0.0, (npk_ml_l * 150.0) + (micro_ml_l * 150.0))
    predicted_k = max(0.0, (npk_ml_l * 150.0) + (micro_ml_l * 360.0))

    pred_record = db.query(models.NPKPrediction).filter(
        models.NPKPrediction.daily_reading_id == reading.id
    ).first()
    if pred_record:
        pred_record.predicted_n = float(predicted_n)
        pred_record.predicted_p = float(predicted_p)
        pred_record.predicted_k = float(predicted_k)
    else:
        db.add(models.NPKPrediction(
            daily_reading_id=reading.id,
            predicted_n=float(predicted_n),
            predicted_p=float(predicted_p),
            predicted_k=float(predicted_k)
        ))
    db.commit()
    return True


def predict_from_crops(reading_id: int, db: Session) -> bool:
    """
    Runs the AI model on all crops linked to a reading, averages the results,
    then updates (or creates) the NPKPrediction record for that reading.
    Supports both single-input (image-only) and multi-modal (image + sensor) models.
    Returns True if prediction was saved, False otherwise.
    """
    if not AI_MODEL:
        return False

    crops = db.query(models.ImageCrop).filter(
        models.ImageCrop.daily_reading_id == reading_id
    ).all()

    if not crops:
        return False

    # Fetch sensor values for this reading
    reading = db.query(models.DailyReading).filter(
        models.DailyReading.id == reading_id
    ).first()

    is_multimodal = len(AI_MODEL.inputs) > 1
    sensor_array  = _normalize_sensors(reading) if (is_multimodal and reading) else None

    crop_preds = []
    for crop in crops:
        if not os.path.exists(crop.crop_path):
            continue
        try:
            img = Image.open(crop.crop_path).convert('RGB').resize((224, 224))
            img_array = np.expand_dims(np.array(img) / 255.0, axis=0)
            if is_multimodal and sensor_array is not None:
                pred = AI_MODEL.predict([img_array, sensor_array], verbose=0)
            else:
                pred = AI_MODEL.predict(img_array, verbose=0)
            crop_preds.append(pred[0])
        except Exception as e:
            print(f"⚠️ predict_from_crops: error on crop {crop.id}: {e}")

    if not crop_preds:
        return False

    avg = np.mean(crop_preds, axis=0)
    npk_ml_l, micro_ml_l = avg

    predicted_n = max(0.0, (npk_ml_l * 80.0) + (micro_ml_l * 80.0))
    predicted_p = max(0.0, (npk_ml_l * 150.0) + (micro_ml_l * 150.0))
    predicted_k = max(0.0, (npk_ml_l * 150.0) + (micro_ml_l * 360.0))

    pred_record = db.query(models.NPKPrediction).filter(
        models.NPKPrediction.daily_reading_id == reading_id
    ).first()

    if pred_record:
        pred_record.predicted_n = float(predicted_n)
        pred_record.predicted_p = float(predicted_p)
        pred_record.predicted_k = float(predicted_k)
    else:
        pred_record = models.NPKPrediction(
            daily_reading_id=reading_id,
            predicted_n=float(predicted_n),
            predicted_p=float(predicted_p),
            predicted_k=float(predicted_k)
        )
        db.add(pred_record)

    db.commit()
    return True


def get_active_bucket_id() -> Optional[str]:
    """Helper to get the current global active_bucket_id."""
    if ACTIVE_BUCKET_GETTER:
        return ACTIVE_BUCKET_GETTER()
    return None

def get_active_experiment_id() -> Optional[str]:
    """Helper to get the current global active_experiment_id."""
    if ACTIVE_EXPERIMENT_GETTER:
        return ACTIVE_EXPERIMENT_GETTER()
    return None

def is_ph_update_requested() -> bool:
    """Helper to check if pH update is requested."""
    if PH_UPDATE_REQUESTED_GETTER:
        return PH_UPDATE_REQUESTED_GETTER()
    return False

class SensorData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    temperature: float = Field(..., validation_alias=AliasChoices("temp", "temperature", "water_temp"))
    ec: float
    ph: float
    # ph_is_estimated: Boolean flag indicating if the pH was simulated (True) 
    # or measured from physical hardware (False). This is part of the Hybrid Data Strategy
    # implemented to bypass the ADC hardware bottleneck for the capstone defense.
    ph_is_estimated: bool = True
    status: str = "active"
    bucket_id: Optional[str] = None
    experiment_id: Optional[str] = None
    timestamp: Optional[datetime] = None

class PHReading(BaseModel):
    timestamp: datetime
    raw_adc: int
    voltage: float

class PHLogPayload(BaseModel):
    device_id: str
    readings: list[PHReading]

class PHUpdatePayload(BaseModel):
    ph: float

@iot_router.post("/logs")
async def create_ph_logs(payload: PHLogPayload):
    """
    Receives batched pH sensor data, logs it to a file, and broadcasts it.
    """
    os.makedirs("logs", exist_ok=True)
    log_file = "logs/ph_sensor.log"
    
    try:
        # 1. Log to file
        with open(log_file, "a") as f:
            for reading in payload.readings:
                log_entry = (
                    f"{reading.timestamp.isoformat()} | "
                    f"device:{payload.device_id} | "
                    f"adc:{reading.raw_adc} | "
                    f"voltage:{reading.voltage:.4f}V\n"
                )
                f.write(log_entry)
        
        # 2. Broadcast to connected clients
        # We broadcast the JSON-serializable version of the payload
        await manager.broadcast(payload.model_dump(mode="json"))
        
        return {"status": "success", "message": f"Logged {len(payload.readings)} readings from {payload.device_id}"}
    except Exception as e:
        print(f"❌ Error logging/broadcasting pH data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@iot_router.post("/experiments/{experiment_id}/update-ph")
async def update_ph(experiment_id: str, payload: PHUpdatePayload, db: Session = Depends(get_db)):
    """
    Finds the oldest reading for the given experiment that needs a pH update,
    and updates it with the provided value.
    """
    # 1. Find the experiment
    experiment = db.query(models.Experiment)\
        .filter(models.Experiment.experiment_id == experiment_id)\
        .first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # 2. Find the oldest pending reading
    reading = db.query(models.DailyReading)\
        .filter(models.DailyReading.experiment_id == experiment.id)\
        .filter(models.DailyReading.needs_ph_update == True)\
        .order_by(models.DailyReading.timestamp.asc())\
        .first()

    if not reading:
        raise HTTPException(
            status_code=404,
            detail="No pending pH updates for this experiment"
        )

    # 3. Update the reading
    old_ph = reading.ph
    reading.ph = payload.ph
    reading.ph_is_estimated = False
    reading.needs_ph_update = False
    
    db.commit()
    db.refresh(reading)

    print(
        f"✅ [update_ph] Updated reading ID {reading.id} for "
        f"experiment {experiment_id}: {old_ph} -> {payload.ph}"
    )

    return {
        "status": "success",
        "updated_reading_id": reading.id,
        "old_ph": old_ph,
        "new_ph": reading.ph,
        "experiment_id": experiment_id
    }

@iot_router.websocket("/ph/stream")
async def websocket_ph_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time pH log streaming.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive by waiting for any message (or just use a ping/pong)
            # In this case, we're just broadcasting FROM the server, so we only need to wait 
            # to know when they disconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"⚠️ WS Stream error: {e}")
        manager.disconnect(websocket)

def capture_frame(output_path: str) -> bool:
    """
    Grabs a single frame from the shared VideoManager and saves it to a file.
    Returns True if successful, False otherwise.
    """
    if VIDEO_MANAGER is None:
        print("❌ VideoManager not initialized in IoT Controller.")
        return False
        
    print(f"📸 Attempting to capture frame from shared VideoManager...")
    frame = VIDEO_MANAGER.get_latest_frame()

    if frame is not None:
        success = cv2.imwrite(output_path, frame)
        if success:
            print(f"✅ Frame saved successfully to {output_path}")
            return True
        else:
            print(f"❌ cv2.imwrite failed to save frame to {output_path}")
            return False

    print(f"❌ Failed to capture frame: No recent frame in VideoManager.")
    return False

def resolve_experiment(db: Session, experiment_id: Optional[str] = None, bucket_label: Optional[str] = None) -> models.Experiment:
    """
    Resolves the experiment to associate data with. 
    Follows priority: payload experiment_id > global active_experiment_id > auto-generated ID.
    Ensures an experiment record is created exactly once in the database.
    """
    # 1. Determine the target experiment_id string
    target_id = None
    
    if experiment_id:
        target_id = experiment_id
    else:
        # Check global state (set by Mobile App)
        target_id = get_active_experiment_id()
    
    if not target_id:
        # Final fallback: Auto-generated ID based on the bucket label
        label = bucket_label or "NPK"
        target_id = f"EXP-{label.upper()}-AUTO"

    # 2. Find existing record or create once
    experiment = db.query(models.Experiment).filter(models.Experiment.experiment_id == target_id).first()
    
    if not experiment:
        print(f"📦 [resolve_experiment] Creating new experiment record: {target_id}")
        experiment = models.Experiment(
            experiment_id=target_id,
            bucket_label=bucket_label or "NPK",
            start_date=datetime.now().date()
        )
        db.add(experiment)
        db.commit()
        db.refresh(experiment)
            
    return experiment

VALID_BUCKET_LABELS = ['NPK', 'Micro', 'Mix', 'Water']

class NewExperimentRequest(BaseModel):
    experiment_id: str
    bucket_label: str
    location: Optional[str] = None

@iot_router.get("/experiments/")
def list_experiments(db: Session = Depends(get_db)):
    """Returns all experiments — used by Pi to let operator select which bucket."""
    experiments = db.query(models.Experiment).order_by(models.Experiment.id).all()
    return [
        {
            "id":            e.id,
            "experiment_id": e.experiment_id,
            "bucket_label":  e.bucket_label,
            "start_date":    str(e.start_date),
        }
        for e in experiments
    ]

@iot_router.post("/experiments/", status_code=201)
def create_experiment(req: NewExperimentRequest, db: Session = Depends(get_db)):
    """Creates a new experiment record — called by Pi when operator selects 'New'."""
    if req.bucket_label not in VALID_BUCKET_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bucket_label '{req.bucket_label}'. Must be one of {VALID_BUCKET_LABELS}"
        )
    existing = db.query(models.Experiment).filter(
        models.Experiment.experiment_id == req.experiment_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Experiment '{req.experiment_id}' already exists.")

    experiment = models.Experiment(
        experiment_id=req.experiment_id,
        bucket_label=req.bucket_label,
        start_date=datetime.now().date()
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return {
        "status":        "created",
        "id":            experiment.id,
        "experiment_id": experiment.experiment_id,
        "bucket_label":  experiment.bucket_label,
        "start_date":    str(experiment.start_date),
    }

@iot_router.post("/sensor_data/", status_code=201)
async def create_sensor_data(data: SensorData, db: Session = Depends(get_db)):
    """
    Receives JSON sensor data from the Raspberry Pi and stores it in the database.
    """
    print(f"📥 [create_sensor_data] Received payload: {data}")

    # Determine bucket label: priority to payload, then global state
    active_id = get_active_bucket_id()
    final_bucket_label = data.bucket_id if data.bucket_id else active_id
    print(f"🪣 [create_sensor_data] Using bucket label: {final_bucket_label}")
    # --- IMAGE CAPTURE ---
    timestamp_now = data.timestamp or datetime.now()
    date_str = timestamp_now.strftime("%Y-%m-%d")
    timestamp_str = timestamp_now.strftime("%Y%m%d_%H%M%S")
    image_filename = f"reading_{final_bucket_label}_{timestamp_str}.jpg"

    # Hierarchical Path: images/YYYY-MM-DD/BucketLabel/filename.jpg
    image_dir = os.path.join("images", date_str, final_bucket_label)
    os.makedirs(image_dir, exist_ok=True)
    image_path = os.path.join(image_dir, image_filename)

    if not capture_frame(image_path):
        print(f"⚠️ [create_sensor_data] Capture failed, continuing without image.")
        image_path = None

    # Resolve experiment
    experiment = resolve_experiment(db, experiment_id=data.experiment_id, bucket_label=final_bucket_label)

    new_reading = models.DailyReading(
        experiment_id=experiment.id,
        ph=data.ph,
        ph_is_estimated=data.ph_is_estimated,
        needs_ph_update=True,
        ec=data.ec,
        water_temp=data.temperature,
        status=data.status,
        image_path=image_path,
        timestamp=data.timestamp or datetime.now()
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    print(f"✅ [create_sensor_data] Successfully saved reading ID: {new_reading.id}")

    return {
        "status": "success",
        "reading_id": new_reading.id,
        "experiment_id": experiment.experiment_id,
        "image_path": image_path
    }

@iot_router.post("/upload_data/")
async def upload_from_iot(
    image: UploadFile,
    ph: float = Form(...),
    ec: float = Form(...),
    temp: float = Form(...),
    bucket_label: str = Form("unknown"),
    experiment_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Receives multipart data (image + sensors) from the Pi and performs AI analysis.
    """
    # A. Save Image
    timestamp_now = datetime.now()
    date_str = timestamp_now.strftime("%Y-%m-%d")
    timestamp_str = timestamp_now.strftime("%Y%m%d_%H%M%S")
    
    # Standard Filename: reading_<TYPE>_<YYYYMMDD>_<HHMMSS>.jpg
    filename = f"reading_{bucket_label}_{timestamp_str}.jpg"
    image_dir = os.path.join("images", date_str, bucket_label)
    os.makedirs(image_dir, exist_ok=True)
    file_path = os.path.join(image_dir, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # B. Find or Create Experiment
    experiment = resolve_experiment(db, experiment_id=experiment_id, bucket_label=bucket_label)

    # C. Save Sensor Data
    reading = models.DailyReading(
        experiment_id=experiment.id,
        image_path=file_path,
        ph=round(ph, 2),
        ph_is_estimated=False,  # This endpoint always starts as estimated
        needs_ph_update=False,
        ec=round(ec, 2),
        water_temp=round(temp, 2)
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    # D. Auto-Cropping & AI Analysis (in-memory, no permanent crop storage)
    crops_analyzed = 0
    if AI_MODEL:
        try:
            img = cv2.imread(file_path)
            if img is not None:
                h, w = img.shape[:2]

                green_crops = [
                    img[y:y + CROP_SIZE, x:x + CROP_SIZE]
                    for x, y in _get_all_crop_coords(w, h, CROP_SIZE)
                    if _is_green_array(img[y:y + CROP_SIZE, x:x + CROP_SIZE])
                ]

                if not green_crops:
                    print("⚠️ No green leaves detected. Falling back to center crop.")
                    cy, cx = h // 2, w // 2
                    y1, x1 = max(0, cy - CROP_SIZE // 2), max(0, cx - CROP_SIZE // 2)
                    green_crops = [img[y1:y1 + CROP_SIZE, x1:x1 + CROP_SIZE]]

                crops_analyzed = len(green_crops)
                if _predict_from_arrays(green_crops, reading, db):
                    print(f"✅ AI Analysis complete using {crops_analyzed} crops.")
                else:
                    print("⚠️ AI prediction failed.")

        except Exception as e:
            print(f"❌ Auto-cropping/AI Error: {e}")
            db.rollback()
    else:
        print("ℹ️ AI_MODEL is None. Creating dummy NPKPrediction for dashboard.")
        db.add(models.NPKPrediction(
            daily_reading_id=reading.id,
            predicted_n=100.0,
            predicted_p=40.0,
            predicted_k=160.0
        ))
        db.commit()

    return {
        "status": "success",
        "message": f"Data processed. Analyzed {crops_analyzed} crops.",
        "crops_count": crops_analyzed
    }
