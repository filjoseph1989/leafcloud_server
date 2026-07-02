from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AlertStatusResponse(BaseModel):
    tank_id: int
    tank_name: str
    has_alert: bool
    level: Optional[str] = None        # "WARNING" | "CRITICAL" | None
    message: Optional[str] = None
    topup_macro_ml: Optional[float] = None
    topup_micro_ml: Optional[float] = None
    last_reading_at: Optional[datetime] = None
