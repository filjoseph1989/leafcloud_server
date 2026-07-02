from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.core.database import Base

class ImageCrop(Base):
    __tablename__ = "image_crops"

    id = Column(Integer, primary_key=True, index=True)
    daily_reading_id = Column(Integer, ForeignKey("daily_readings.id"))
    crop_path = Column(String(255))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    crop_type = Column(String(50), server_default="grid")
