import os
import shutil
from datetime import datetime
from fastapi import FastAPI, UploadFile, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image
from dotenv import load_dotenv

from database import get_db, engine, Base
import models
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

load_dotenv()

# --- Global State ---
active_bucket_id: Optional[str] = None

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

class SensorData(BaseModel):
    temperature: float = Field(..., alias="temp", validation_alias="temperature")
    ec: float
    ph: float
    status: str = "active"
    bucket_id: Optional[str] = None
    timestamp: datetime = None

    class Config:
        populate_by_name = True


# Load AI Brain (Mock loader for now if file doesn't exist)
try:
    import tensorflow as tf
    model = tf.keras.models.load_model("leafcloud_mobilenetv2_model.h5")
    print("🧠 AI Model loaded successfully.")
except Exception as e:
    print(f"⚠️ AI Model not found or failed to load: {e}. Using dummy predictions.")
    model = None

app = FastAPI(
    title="LEAFCLOUD API",
    description="Production Backend for LEAFCLOUD System",
    version="2.0.0"
)

# Ensure images directory exists and mount it to serve files via HTTP
os.makedirs("images", exist_ok=True)
app.mount("/images", StaticFiles(directory="images"), name="images")

# --- CONTROL ENDPOINTS ---
@app.post("/control/active-bucket")
def set_active_bucket(request: ActiveBucketRequest):
    """
    Updates the global active_bucket_id based on the provided label.
    'STOP' sets the ID back to None.

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

@app.get("/control/current-status")
def get_current_status():
    """
    Returns the current active_bucket_id.

    Returns:
        A dictionary containing the current active_bucket_id.
    """
    return {"active_bucket_id": active_bucket_id}

# --- 1. AUTHENTICATION ENDPOINT ---
@app.post("/auth/login")
def login(request: LoginRequest):
    """
    Simple authentication endpoint for the mobile app prototype.
    Currently uses hardcoded credentials.

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

# --- 2. ENDPOINT FOR IOT (Raspberry Pi uses this) ---
@app.post("/iot/sensor_data/", status_code=201)
async def create_sensor_data(data: SensorData, db: Session = Depends(get_db)):
    """
    Receives JSON sensor data from the Raspberry Pi and stores it in the database.

    Args:
        data: A SensorData object containing readings and optional bucket_id.
        db: The database session.

    Returns:
        A dictionary confirming success and the processed data.
    """
    print(f"📥 [create_sensor_data] Received payload: {data}")

    # Determine bucket label: priority to payload, then global state
    final_bucket_label = data.bucket_id if data.bucket_id else active_bucket_id
    print(f"🪣 [create_sensor_data] Using bucket label: {final_bucket_label}")

    # For now, we associate with a default experiment or create one if none exists
    experiment = db.query(models.Experiment).first()
    if not experiment:
        experiment = models.Experiment(bucket_label="default", start_date=datetime.now().date())
        db.add(experiment)
        db.commit()
        db.refresh(experiment)

    new_reading = models.DailyReading(
        bucket_id=experiment.id,
        ph=data.ph,
        ec=data.ec,
        water_temp=data.temperature,
        status=data.status,
        bucket_label=final_bucket_label,
        timestamp=data.timestamp or datetime.now()
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    print(f"✅ [create_sensor_data] Successfully saved reading ID: {new_reading.id} with bucket: {final_bucket_label}")

    return {"status": "success", "data": data}

# --- 3. VIDEO STREAMING PROXY ---
def capture_frame(source_url: str, output_path: str) -> bool:
    """
    Grabs a single frame from the video stream and saves it to a file.
    Returns True if successful, False otherwise.
    """
    import cv2
    import time

    print(f"📸 Attempting to capture frame from {source_url}...")
    cap = cv2.VideoCapture(source_url)
    
    if not cap.isOpened():
        print(f"❌ Could not open video source: {source_url}")
        return False

    # Try to read a frame (give it a few attempts in case of delay)
    success = False
    frame = None
    for i in range(5):
        success, frame = cap.read()
        if success:
            break
        time.sleep(0.1)

    if success and frame is not None:
        cv2.imwrite(output_path, frame)
        print(f"✅ Frame saved to {output_path}")
        cap.release()
        return True
    
    print(f"❌ Failed to capture frame from {source_url}")
    cap.release()
    return False

@app.get("/video_feed")
async def video_feed():
    """
    Proxies MJPEG stream from the source (e.g., Raspberry Pi) to the client.
    """
    import cv2
    import time
    source_url = os.getenv("VIDEO_STREAM_URL", "udp://0.0.0.0:5000")

    def generate():
        print(f"📹 Connecting to video stream at {source_url}...")
        cap = cv2.VideoCapture(source_url)
        frame_count = 0

        while True:
            success, frame = cap.read()
            if not success:
                # Log failure (throttled by the sleep below)
                print(f"⚠️ No video signal from {source_url}")

                # Fallback: Generate a "NO SIGNAL" placeholder if stream is missing
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, "NO SIGNAL", (220, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(frame, f"Waiting for {source_url}...", (10, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                # Sleep briefly to avoid high CPU usage while waiting
                time.sleep(1.0)
            else:
                # Log success occasionally (every ~100 frames / ~3 seconds at 30fps)
                if frame_count % 100 == 0:
                    h, w, _ = frame.shape
                    print(f"✅ Receiving video frame #{frame_count} ({w}x{h}) from {source_url}")
                frame_count += 1

            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue

            yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        cap.release()

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/iot/upload_data/")
async def upload_from_iot(
    image: UploadFile,
    ph: float = Form(...),
    ec: float = Form(...),
    temp: float = Form(...),
    bucket_label: str = Form("unknown"), # Added to link to experiment
    db: Session = Depends(get_db)
):
    # A. Save Image
    os.makedirs("images", exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{image.filename}"
    file_path = os.path.join("images", filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # B. Find or Create Experiment (Simplified logic)
    # In a real app, you might look up by bucket_label
    experiment = db.query(models.Experiment).filter(models.Experiment.bucket_label == bucket_label).first()
    if not experiment:
        experiment = models.Experiment(bucket_label=bucket_label, start_date=datetime.now().date())
        db.add(experiment)
        db.commit()
        db.refresh(experiment)

    # C. Save Sensor Data
    reading = models.DailyReading(
        bucket_id=experiment.id,
        image_path=file_path,
        ph=ph,
        ec=ec,
        water_temp=temp
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)

    # D. Run AI (Server-Side Processing)
    predicted_n, predicted_p, predicted_k = 0.0, 0.0, 0.0

    if model:
        try:
            img = Image.open(file_path).convert('RGB').resize((224, 224))
            img_array = np.expand_dims(np.array(img) / 255.0, axis=0)
            prediction = model.predict(img_array)
            predicted_n, predicted_p, predicted_k = prediction[0]
        except Exception as e:
            print(f"Prediction Error: {e}")
    else:
        # Dummy fallback if model isn't loaded
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