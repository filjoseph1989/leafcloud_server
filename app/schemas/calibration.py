from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorCalibrationBase(BaseModel):
    sensor_name: str
    is_calibrating: bool

class SensorCalibration(SensorCalibrationBase):
    id: int
    updated_at: datetime

    class Config:
        from_attributes = True

class SensorCalibrationUpdate(BaseModel):
    is_calibrating: bool
