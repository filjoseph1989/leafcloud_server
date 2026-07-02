from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TelemetryPost(BaseModel):
    tank_id: int
    ph: Optional[float] = None
    ec: Optional[float] = None
    water_temp: Optional[float] = None

class TelemetryResponse(BaseModel):
    tank_id: int
    ph: Optional[float] = None
    ec: Optional[float] = None
    water_temp: Optional[float] = None
    updated_at: datetime

    class Config:
        from_attributes = True
