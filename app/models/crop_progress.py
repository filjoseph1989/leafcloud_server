from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.core.database import Base

class ImageCropProgress(Base):
    __tablename__ = "image_crop_progress"

    id = Column(Integer, primary_key=True, index=True)
    rel_path = Column(String(255), unique=True, index=True)
    is_processed = Column(Boolean)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    locked_until = Column(DateTime(timezone=True))
    additional_processed = Column(Boolean, default=False)
