from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class HistoryItem(BaseModel):
    reading_id: int
    timestamp: datetime
    image_url: str
    ph: float
    ec: float
    water_temp: float
    predicted_n: Optional[float] = None
    predicted_p: Optional[float] = None
    predicted_k: Optional[float] = None
    macro_scale: Optional[float] = None
    micro_scale: Optional[float] = None

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    tank_id: int
    tank_name: str
    days: int
    total: int
    readings: List[HistoryItem]
