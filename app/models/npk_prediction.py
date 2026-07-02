from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, func
from app.core.database import Base

class NPKPrediction(Base):
    __tablename__ = "npk_predictions"

    id = Column(Integer, primary_key=True, index=True)
    daily_reading_id = Column(Integer, ForeignKey("daily_readings.id"))
    
    # Classification Output
    predicted_class = Column(String, default="Unknown")
    is_anomaly = Column(Boolean, default=False)
    
    # Regression Outputs (Legacy)
    predicted_n = Column(Float)
    predicted_p = Column(Float)
    predicted_k = Column(Float)
    
    # Regression Outputs (New Scales)
    macro_scale = Column(Float)
    micro_scale = Column(Float)
    confidence_score = Column(Float)
    prediction_date = Column(DateTime(timezone=True), server_default=func.now())
