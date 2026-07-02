from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, Query
from sqlalchemy.orm import Session
import os
import uuid
from datetime import datetime
import shutil
from typing import Optional

from app.core.database import get_db
from app.core.config import settings
from app.models.tank_config import TankConfig
from app.models.npk_prediction import NPKPrediction
from app.models.daily_reading import DailyReading
from app.models.live_telemetry import LiveTelemetry
from app.schemas.telemetry import TelemetryPost, TelemetryResponse
from app.schemas.dashboard import DashboardResponse, TelemetryData, NutrientEstimation, ActionableAlert, AdvisoryInsight
from app.schemas.history import HistoryResponse
from app.schemas.alert import AlertStatusResponse
from app.services.ai_service import process_iot_data_background
from app.services.history_service import get_tank_history
from app.services.alert_service import get_tank_alert_status
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()
#dri nga part, dri mag request ang mobile ug data (line has 47-147)
@router.get("/dashboard/{tank_id}", response_model=DashboardResponse)
def get_tank_dashboard(tank_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Returns the real-time monitoring dashboard data for a specific tank.
    Performs the dynamic math to convert AI scales into physical grams and alerts.
    """
    # 1. Fetch Config
    tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail="Tank configuration not found")

    # 2. Fetch Latest Reading
    latest_reading = db.query(DailyReading).filter(
        DailyReading.tank_id == tank_id
    ).order_by(DailyReading.timestamp.desc()).first()

    if not latest_reading:
        raise HTTPException(status_code=404, detail="No readings found for this tank")

    # 3. Fetch AI Prediction for that reading
    prediction = db.query(NPKPrediction).filter(
        NPKPrediction.daily_reading_id == latest_reading.id
    ).first()

    # Regression scales drive the nutrient math
    macro_scale = prediction.macro_scale if prediction and prediction.macro_scale is not None else 1.0
    micro_scale = prediction.micro_scale if prediction and prediction.micro_scale is not None else 1.0

    # Classification output for display only (does not affect math)
    predicted_class = prediction.predicted_class if prediction and prediction.predicted_class else "Unknown"
    profile = {
        "Mix": "Balanced Mix",
        "NPK": "Macro-Leaning Blend",
        "Micro": "Micro-Leaning Blend",
        "Water": "Water Only (No Nutrients)",
    }.get(predicted_class, "Unknown")

    # 4. PERFORM DYNAMIC MATH
    # Grams = (Scaling Index * Target Dosage mL/L * Tank Volume L * Density g/mL) * (NPK % / 100)
    
    # Calculate Macro Contribution
    macro_weight_total = tank.target_macro_dosage_mll * tank.water_volume_liters * tank.macro_density
    n_from_macro = (macro_scale * macro_weight_total) * (tank.macro_n_pct / 100)
    p_from_macro = (macro_scale * macro_weight_total) * (tank.macro_p_pct / 100)
    k_from_macro = (macro_scale * macro_weight_total) * (tank.macro_k_pct / 100)

    # Calculate Micro Contribution
    micro_weight_total = tank.target_micro_dosage_mll * tank.water_volume_liters * tank.micro_density
    n_from_micro = (micro_scale * micro_weight_total) * (tank.micro_n_pct / 100)
    p_from_micro = (micro_scale * micro_weight_total) * (tank.micro_p_pct / 100)
    k_from_micro = (micro_scale * micro_weight_total) * (tank.micro_k_pct / 100)

    # 5. Convert Physical Mass (Grams) to Concentration (PPM)
    total_grams = n_from_macro + p_from_macro + k_from_macro + n_from_micro + p_from_micro + k_from_micro

    # 1 mg/L = 1 PPM. Multiply grams by 1000 to get mg, then divide by Liters safely.
    vol = tank.water_volume_liters
    n_ppm = ((n_from_macro + n_from_micro) * 1000) / vol if vol > 0 else 0
    p_ppm = ((p_from_macro + p_from_micro) * 1000) / vol if vol > 0 else 0
    k_ppm = ((k_from_macro + k_from_micro) * 1000) / vol if vol > 0 else 0
    total_ppm = (total_grams * 1000) / vol if vol > 0 else 0

    if prediction and getattr(prediction, 'is_anomaly', False):
        advisory_sum = "AI Sensor Anomaly Detected"
        advisory_exp = f"Conflicting data! The AI classified this tank visually as '{predicted_class}' but physical sensors read 0."
        advisory_act = "Please manually inspect the tank, check the nutrient solution, and recalibrate your pH/EC sensors."
    elif macro_scale >= 0.9 and micro_scale >= 0.9:
        advisory_sum = "Optimal Nutrient Balance"
        advisory_exp = f"Your {tank.tank_name} has a stable concentration of approximately {round(total_ppm)} PPM (Total NPK). The plants are currently in a high-nutrition environment."
        advisory_act = "No immediate action required. Maintain current environmental conditions."
    elif macro_scale < 0.7 or micro_scale < 0.7:
        advisory_sum = "Nutrient Depletion Detected"
        advisory_exp = f"Nutrient levels have dropped significantly. There is only {round(total_ppm)} PPM of total nutrients remaining."
        advisory_act = "Follow the Top-up instructions below to restore the optimal nutrient balance."
    else:
        advisory_sum = "Moderate Concentration"
        advisory_exp = f"Nutrients are at stable but declining levels. Total NPK concentration is {round(total_ppm)} PPM."
        advisory_act = "Monitor closely. Top-up may be required within the next 24-48 hours."

    alert = None
    if macro_scale < 0.7 or micro_scale < 0.7:
        topup_macro = max(0, (1.0 - macro_scale) * tank.target_macro_dosage_mll * tank.water_volume_liters)
        topup_micro = max(0, (1.0 - micro_scale) * tank.target_micro_dosage_mll * tank.water_volume_liters)
        
        alert = ActionableAlert(
            level="WARNING",
            message=f"Nutrient levels have dropped to {int(min(macro_scale, micro_scale)*100)}% of recommended dosage.",
            action_required=True,
            topup_macro_ml=round(topup_macro, 1),
            topup_micro_ml=round(topup_micro, 1)
        )

    # 7. Construct Response
    return DashboardResponse(
        tank_id=tank.id,
        tank_name=tank.tank_name,
        last_updated=latest_reading.timestamp,
        image_url=str(request.base_url).rstrip("/") + "/" + latest_reading.image_path.replace("\\", "/") if latest_reading.image_path else "",
        health_status="HEALTHY" if macro_scale > 0.8 else "NUTRIENT DEFICIENT",
        profile_detected=profile,
        predicted_class=predicted_class,
        is_anomaly=prediction.is_anomaly if prediction and prediction.is_anomaly is not None else False,
        macro_scale=macro_scale,
        micro_scale=micro_scale,
        telemetry=TelemetryData(
            ph=latest_reading.ph,
            ec=latest_reading.ec,
            water_temp=latest_reading.water_temp,
            status="Safe Range" if 5.5 <= latest_reading.ph <= 6.5 else "Action Needed"
        ),
        estimated_nutrients=NutrientEstimation(
            n_ppm=round(n_ppm, 1),
            p_ppm=round(p_ppm, 1),
            k_ppm=round(k_ppm, 1),
            total_estimated_ppm=round(total_ppm, 1)
        ),
        advisory=AdvisoryInsight(
            summary=advisory_sum,
            explanation=advisory_exp,
            farmer_action=advisory_act
        ),
        alert=alert
    )
#dri nga part, dri magsend ang ioT (line 149-218)
@router.post("/upload")
async def upload_iot_data(
    background_tasks: BackgroundTasks,
    tank_id: int = Form(...),
    ph: float = Form(...),
    ec: float = Form(...),
    temp: float = Form(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    Endpoint for Raspberry Pi to upload sensor data and images.
    Uses tank_id to link the data dynamically.
    """
    # 1. Verify Tank exists
    tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank with ID {tank_id} not found")

    # 2. Prepare Storage Path
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    
    file_path = None
    if image and image.filename:
        # images/{date}/{tank_name}/
        folder_path = os.path.join(settings.SOURCE_DIR, date_str, tank.tank_name.replace(" ", "_"))
        os.makedirs(folder_path, exist_ok=True)
        
        file_extension = os.path.splitext(image.filename)[1]
        filename = f"reading_{timestamp_str}_{uuid.uuid4().hex[:6]}{file_extension}"
        file_path = os.path.join(folder_path, filename)

        # 3. Save Image to Disk
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save image: {e}")

    # 4. Create Database Entry
    daily_reading = DailyReading(
        timestamp=now,
        image_path=file_path.replace("\\", "/") if file_path else None,
        ph=ph,
        ec=ec,
        water_temp=temp,
        tank_id=tank_id,
        is_new_data=True
    )
    db.add(daily_reading)
    db.commit()
    db.refresh(daily_reading)

    # 5. Trigger Background AI Tasks (Crop + Predict) if image is present
    if daily_reading.image_path:
        background_tasks.add_task(process_iot_data_background, daily_reading.id)

    return {
        "status": "success",
        "message": "Data received and saved",
        "reading_id": daily_reading.id
    }


@router.get("/alert/{tank_id}", response_model=AlertStatusResponse)
def get_tank_alert(tank_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank with ID {tank_id} not found")

    return get_tank_alert_status(db, tank)

#dri nga part, dri ang kwaon ang history katong sa mobile 
@router.get("/history/{tank_id}", response_model=HistoryResponse)
def get_tank_history_endpoint(
    tank_id: int,
    request: Request,
    db: Session = Depends(get_db),
    days: int = Query(default=7, ge=1, le=90, description="Number of past days to fetch"),
    limit: int = Query(default=200, ge=1, le=200, description="Maximum number of readings to return"),
    current_user: User = Depends(get_current_user),
):
    tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank with ID {tank_id} not found")

    return get_tank_history(db, tank, days, limit, str(request.base_url))


@router.post("/telemetry", response_model=dict)
def update_telemetry(payload: TelemetryPost, db: Session = Depends(get_db)):
    """
    Endpoint for Raspberry Pi to upload high-frequency live sensor readings.
    Updates the single-row cache for the specified tank.
    """
    # 1. Verify Tank exists
    tank = db.query(TankConfig).filter(TankConfig.id == payload.tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail=f"Tank with ID {payload.tank_id} not found")

    # 2. Get or create LiveTelemetry entry
    telemetry = db.query(LiveTelemetry).filter(LiveTelemetry.tank_id == payload.tank_id).first()
    if not telemetry:
        telemetry = LiveTelemetry(tank_id=payload.tank_id)
        db.add(telemetry)

    # 3. Update fields if provided in the payload
    if payload.ph is not None:
        telemetry.ph = payload.ph
    if payload.ec is not None:
        telemetry.ec = payload.ec
    if payload.water_temp is not None:
        telemetry.water_temp = payload.water_temp

    db.commit()
    return {"status": "success", "message": "Telemetry updated"}


@router.get("/telemetry/{tank_id}", response_model=TelemetryResponse)
def get_live_telemetry(tank_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Returns the real-time live telemetry readings for a specific tank.
    """
    # 1. Verify Tank exists
    tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail="Tank configuration not found")

    # 2. Fetch Live Telemetry
    telemetry = db.query(LiveTelemetry).filter(LiveTelemetry.tank_id == tank_id).first()
    if not telemetry:
        # Fallback: check if there's any daily reading
        latest_reading = db.query(DailyReading).filter(
            DailyReading.tank_id == tank_id
        ).order_by(DailyReading.timestamp.desc()).first()
        
        if latest_reading:
            telemetry = LiveTelemetry(
                tank_id=tank_id,
                ph=latest_reading.ph,
                ec=latest_reading.ec,
                water_temp=latest_reading.water_temp,
                updated_at=latest_reading.timestamp
            )
            db.add(telemetry)
            db.commit()
            db.refresh(telemetry)
        else:
            raise HTTPException(status_code=404, detail="No telemetry or daily readings found for this tank")

    return telemetry
