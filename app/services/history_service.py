from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.daily_reading import DailyReading
from app.models.npk_prediction import NPKPrediction
from app.models.tank_config import TankConfig
from app.schemas.history import HistoryItem, HistoryResponse

MAX_LIMIT = 200


def get_tank_history(
    db: Session,
    tank: TankConfig,
    days: int,
    limit: int,
    base_url: str,
) -> HistoryResponse:
    since = datetime.now() - timedelta(days=days)
    safe_limit = min(limit, MAX_LIMIT)

    rows = (
        db.query(DailyReading, NPKPrediction)
        .outerjoin(NPKPrediction, NPKPrediction.daily_reading_id == DailyReading.id)
        .filter(DailyReading.tank_id == tank.id)
        .filter(DailyReading.timestamp >= since)
        .order_by(DailyReading.timestamp.desc())
        .limit(safe_limit)
        .all()
    )

    items = [_to_history_item(reading, prediction, base_url) for reading, prediction in rows]

    return HistoryResponse(
        tank_id=tank.id,
        tank_name=tank.tank_name,
        days=days,
        total=len(items),
        readings=items,
    )


def _to_history_item(reading: DailyReading, prediction: NPKPrediction | None, base_url: str) -> HistoryItem:
    return HistoryItem(
        reading_id=reading.id,
        timestamp=reading.timestamp,
        image_url=base_url.rstrip("/") + "/" + reading.image_path.replace("\\", "/"),
        ph=reading.ph,
        ec=reading.ec,
        water_temp=reading.water_temp,
        predicted_n=prediction.predicted_n if prediction else None,
        predicted_p=prediction.predicted_p if prediction else None,
        predicted_k=prediction.predicted_k if prediction else None,
        macro_scale=prediction.macro_scale if prediction else None,
        micro_scale=prediction.micro_scale if prediction else None,
    )
