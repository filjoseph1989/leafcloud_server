from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, func, ForeignKey
from app.core.database import Base

class DailyReading(Base):
    __tablename__ = "daily_readings"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    image_path = Column(String(255))
    ph = Column(Float)
    ec = Column(Float)
    water_temp = Column(Float)
    tank_id = Column(Integer, ForeignKey("tank_configs.id"))
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=True)
    is_new_data = Column(Boolean, default=False)
