from sqlalchemy.orm import Session
from app.models.daily_reading import DailyReading
from app.models.npk_prediction import NPKPrediction
from app.models.tank_config import TankConfig
from app.schemas.alert import AlertStatusResponse


def get_tank_alert_status(db: Session, tank: TankConfig) -> AlertStatusResponse:
    latest_reading = (
        db.query(DailyReading)
        .filter(DailyReading.tank_id == tank.id)
        .order_by(DailyReading.timestamp.desc())
        .first()
    )

    if not latest_reading:
        return AlertStatusResponse(
            tank_id=tank.id,
            tank_name=tank.tank_name,
            has_alert=False,
        )

    prediction = (
        db.query(NPKPrediction)
        .filter(NPKPrediction.daily_reading_id == latest_reading.id)
        .first()
    )

    macro_scale = prediction.macro_scale if prediction and prediction.macro_scale is not None else 1.0
    micro_scale = prediction.micro_scale if prediction and prediction.micro_scale is not None else 1.0
    min_scale = min(macro_scale, micro_scale)

    if min_scale >= 0.7:
        return AlertStatusResponse(
            tank_id=tank.id,
            tank_name=tank.tank_name,
            has_alert=False,
            last_reading_at=latest_reading.timestamp,
        )

    level = "CRITICAL" if min_scale < 0.5 else "WARNING"
    topup_macro = max(0.0, (1.0 - macro_scale) * tank.target_macro_dosage_mll * tank.water_volume_liters)
    topup_micro = max(0.0, (1.0 - micro_scale) * tank.target_micro_dosage_mll * tank.water_volume_liters)

    return AlertStatusResponse(
        tank_id=tank.id,
        tank_name=tank.tank_name,
        has_alert=True,
        level=level,
        message=f"Nutrient levels at {int(min_scale * 100)}% of target. Top-up required.",
        topup_macro_ml=round(topup_macro, 1),
        topup_micro_ml=round(topup_micro, 1),
        last_reading_at=latest_reading.timestamp,
    )
