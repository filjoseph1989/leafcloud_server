from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.core.database import Base

class AutomatedActionLog(Base):
    __tablename__ = "automated_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255))
    original_path = Column(String(500))
    current_path = Column(String(500))
    action_type = Column(String(100))
    reason = Column(String(255))
    metric_value = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
