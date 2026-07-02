from sqlalchemy import Column, Integer, String, Float, Date, Boolean
from app.core.database import Base

class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    bucket_label = Column(String(50))
    start_date = Column(Date)
    experiment_id = Column(String(50), unique=True, index=True)
    is_current = Column(Boolean, nullable=False, default=False)
    bucket_volume = Column(Float)
    n_ratio = Column(Float)
    p_ratio = Column(Float)
    k_ratio = Column(Float)
    target_dosage = Column(Float)
