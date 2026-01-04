import os
import shutil
from datetime import datetime
from fastapi import FastAPI, UploadFile, Form, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image

from database import get_db, engine, Base
import models

# Ensure tables exist
Base.metadata.create_all(bind=engine)

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

def generate_recommendation(n, p, k, ph, ec):
    """
    Rule-based engine to convert sensor/AI data into actionable advice.
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
    return "System healthy. No action required."

# --- 2. ENDPOINT FOR IOT (Raspberry Pi uses this) ---
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)