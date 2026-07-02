from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, func
from app.core.database import Base

class LiveTelemetry(Base):
    __tablename__ = "live_telemetries"

    tank_id = Column(Integer, ForeignKey("tank_configs.id", ondelete="CASCADE"), primary_key=True, index=True)
    ph = Column(Float, nullable=True)
    ec = Column(Float, nullable=True)
    water_temp = Column(Float, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
