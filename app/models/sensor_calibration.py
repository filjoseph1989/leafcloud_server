from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.core.database import Base

class SensorCalibration(Base):
    __tablename__ = "sensor_calibrations"

    id = Column(Integer, primary_key=True, index=True)
    sensor_name = Column(String(100), unique=True, index=True)
    is_calibrating = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
