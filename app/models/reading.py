from sqlalchemy import Column, BigInteger, String, Float, DateTime, Index, Integer
from app.core.database import Base

class CleanedDailyReading(Base):
    __tablename__ = "cleaned_daily_readings"

    id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime(timezone=True))
    image_path = Column(String)
    ph = Column(Float)
    ec = Column(Float)
    water_temp = Column(Float)
    experiment_id = Column(BigInteger)
    tank_id = Column(Integer)
    __table_args__ = (
        Index("idx_cleaned_exp_id", "experiment_id"),
        Index("idx_cleaned_timestamp", "timestamp"),
    )
