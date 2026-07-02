from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import logging
import asyncio

from app.core.database import get_db
from app.models.sensor_calibration import SensorCalibration as SensorCalibrationModel
from app.schemas.calibration import SensorCalibration, SensorCalibrationUpdate

logger = logging.getLogger(__name__)
router = APIRouter()

# Safety timeout (auto-cancel calibration after 2 minutes)
CALIBRATION_TIMEOUT_SECONDS = 120

async def auto_timeout_calibration(calibration_id: int):
    """
    Background worker that acts as a fallback.
    If the hardware fails to report back within the timeout period,
    the server resets the status to false.
    """
    logger.info(f"⏰ Starting safety timeout ({CALIBRATION_TIMEOUT_SECONDS}s) for calibration ID {calibration_id}")
    await asyncio.sleep(CALIBRATION_TIMEOUT_SECONDS)
    
    # We must obtain a new DB session because the request session will be closed
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        calibration = db.query(SensorCalibrationModel).filter(SensorCalibrationModel.id == calibration_id).first()
        if calibration and calibration.is_calibrating:
            logger.warning(f"⏰ Safety timeout reached for calibration ID {calibration_id}. Auto-resetting is_calibrating to False.")
            calibration.is_calibrating = False
            db.commit()
    except Exception as e:
        logger.error(f"Error in auto_timeout_calibration: {e}")
    finally:
        db.close()

@router.get("/", response_model=List[SensorCalibration])
def get_all_calibrations(db: Session = Depends(get_db)):
    """Retrieve all sensor calibration states."""
    return db.query(SensorCalibrationModel).all()

@router.get("/{calibration_id}", response_model=SensorCalibration)
def get_calibration_by_id(calibration_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific sensor calibration state by ID."""
    calibration = db.query(SensorCalibrationModel).filter(SensorCalibrationModel.id == calibration_id).first()
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration record not found")
    return calibration

@router.patch("/{calibration_id}", response_model=SensorCalibration)
def update_calibration_state(
    calibration_id: int, 
    update: SensorCalibrationUpdate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Update the is_calibrating state of a sensor and handle background timeout tasks."""
    calibration = db.query(SensorCalibrationModel).filter(SensorCalibrationModel.id == calibration_id).first()
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration record not found")
    
    was_calibrating = calibration.is_calibrating
    calibration.is_calibrating = update.is_calibrating
    db.commit()
    db.refresh(calibration)
    
    # Trigger dispatch log and background safety timeout if starting calibration
    if calibration.is_calibrating and not was_calibrating:
        logger.info(f"📡 Dispatching start command for sensor {calibration.sensor_name} (ID: {calibration_id}) via HTTP polling.")
        background_tasks.add_task(auto_timeout_calibration, calibration_id)
    elif not calibration.is_calibrating and was_calibrating:
        logger.info(f"📡 Dispatching stop command/reset for sensor {calibration.sensor_name} (ID: {calibration_id}).")
        
    return calibration

@router.post("/{calibration_id}/complete")
def complete_calibration(
    calibration_id: int,
    result: dict = None,
    db: Session = Depends(get_db)
):
    """Callback endpoint called by the microcontroller/hardware when calibration is completed."""
    calibration = db.query(SensorCalibrationModel).filter(SensorCalibrationModel.id == calibration_id).first()
    if not calibration:
        raise HTTPException(status_code=404, detail="Calibration record not found")
    
    logger.info(f"✅ Hardware completed calibration for sensor {calibration.sensor_name} (ID: {calibration_id}). Result: {result}")
    
    calibration.is_calibrating = False
    db.commit()
    db.refresh(calibration)
    return {"status": "success", "calibration": {
        "id": calibration.id,
        "sensor_name": calibration.sensor_name,
        "is_calibrating": calibration.is_calibrating,
        "updated_at": calibration.updated_at.isoformat() if calibration.updated_at else None
    }}

