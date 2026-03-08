import os
import shutil
import cv2
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image

from database import get_db
import models
from pydantic import BaseModel, Field, ConfigDict, AliasChoices

# The router for all IoT-related endpoints
iot_router = APIRouter(prefix="/iot", tags=["IoT"])

# Internal references that will be injected or accessed globally
AI_MODEL = None
VIDEO_MANAGER = None
ACTIVE_BUCKET_GETTER = None
ACTIVE_EXPERIMENT_GETTER = None

def init_iot_controller(model=None, video_manager=None, bucket_getter=None, experiment_getter=None):
    """Initializes the controller with necessary global state."""
    global AI_MODEL, VIDEO_MANAGER, ACTIVE_BUCKET_GETTER, ACTIVE_EXPERIMENT_GETTER
    AI_MODEL = model
    VIDEO_MANAGER = video_manager
    ACTIVE_BUCKET_GETTER = bucket_getter
    ACTIVE_EXPERIMENT_GETTER = experiment_getter

def get_active_bucket_id():
    """Helper to get the current global active_bucket_id."""
    if ACTIVE_BUCKET_GETTER:
        return ACTIVE_BUCKET_GETTER()
    return None

def get_active_experiment_id():
    """Helper to get the current global active_experiment_id."""
    if ACTIVE_EXPERIMENT_GETTER:
        return ACTIVE_EXPERIMENT_GETTER()
    return None

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
        cv2.imwrite(output_path, frame)
        print(f"✅ Frame saved to {output_path}")
        return True

    print(f"❌ Failed to capture frame: No recent frame in VideoManager.")
    return False

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
    timestamp_str = (data.timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    image_filename = f"reading_{final_bucket_label}_{timestamp_str}.jpg"
    os.makedirs("images", exist_ok=True)
    image_path = os.path.join("images", image_filename)

    if not capture_frame(image_path):
        print(f"⚠️ [create_sensor_data] Capture failed, continuing without image.")
        image_path = None

    # Associate with an experiment
    if data.experiment_id:
        experiment = db.query(models.Experiment).filter(models.Experiment.experiment_id == data.experiment_id).first()
        if not experiment:
            raise HTTPException(status_code=400, detail=f"Experiment '{data.experiment_id}' not found.")
    else:
        # Fallback: check global active_experiment_id first
        active_exp_id = get_active_experiment_id()
        if active_exp_id:
            experiment = db.query(models.Experiment).filter(models.Experiment.experiment_id == active_exp_id).first()
        else:
            experiment = None

        # Fallback: newest experiment
        if not experiment:
            experiment = db.query(models.Experiment).order_by(desc(models.Experiment.id)).first()
        
        # If still no experiment (clean DB), create a default one
        if not experiment:
            print("📦 [create_sensor_data] No experiments found. Creating default 'EXP-DEFAULT'.")
            experiment = models.Experiment(
                experiment_id="EXP-DEFAULT",
                bucket_label="NPK",
                start_date=datetime.now().date()
            )
            db.add(experiment)
            db.commit()
            db.refresh(experiment)

    new_reading = models.DailyReading(
        experiment_id=experiment.id,
        ph=data.ph,
        ph_is_estimated=data.ph_is_estimated,
        ec=data.ec,
        water_temp=data.temperature,
        status=data.status,
        bucket_label=final_bucket_label,
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
    db: Session = Depends(get_db)
):
    """
    Receives multipart data (image + sensors) from the Pi and performs AI analysis.
    """
    # A. Save Image
    os.makedirs("images", exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{image.filename}"
    file_path = os.path.join("images", filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # B. Find or Create Experiment
    # Note: For now, we search by bucket_label as fallback if no global context, 
    # but the goal is to link to the newest experiment if bucket matches.
    experiment = db.query(models.Experiment).filter(models.Experiment.bucket_label == bucket_label).order_by(desc(models.Experiment.id)).first()
    if not experiment:
        # Fallback: just newest experiment
        experiment = db.query(models.Experiment).order_by(desc(models.Experiment.id)).first()
    
    if not experiment:
         raise HTTPException(status_code=400, detail="No active experiment found. Create one first.")

    # C. Save Sensor Data
    reading = models.DailyReading(
        experiment_id=experiment.id,
        image_path=file_path,
        ph=ph,
        ec=ec,
        water_temp=temp
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    # D. Run AI
    predicted_n, predicted_p, predicted_k = 0.0, 0.0, 0.0

    if AI_MODEL:
        try:
            img = Image.open(file_path).convert('RGB').resize((224, 224))
            img_array = np.expand_dims(np.array(img) / 255.0, axis=0)
            prediction = AI_MODEL.predict(img_array)
            predicted_n, predicted_p, predicted_k = prediction[0]
        except Exception as e:
            print(f"Prediction Error: {e}")
    else:
        # Dummy fallback
        predicted_n, predicted_p, predicted_k = 150.0, 50.0, 200.0

    # E. Save Prediction
    pred_record = models.NPKPrediction(
        daily_reading_id=reading.id,
        predicted_n=float(predicted_n),
        predicted_p=float(predicted_p),
        predicted_k=float(predicted_k)
    )
    db.add(pred_record)
    db.commit()

    return {"status": "success", "message": "Data processed and NPK calculated"}
