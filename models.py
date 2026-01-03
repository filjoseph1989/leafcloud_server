from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Experiment(Base):
    """
    Batch Tracker: Organizes data by crop cycle (e.g., "Lettuce Batch Oct 2026").
    """
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    bucket_label = Column(String(50))
    start_date = Column(Date)

    # Relationship
    readings = relationship("DailyReading", back_populates="experiment")

class DailyReading(Base):
    """
    Input Log: Merges image and sensor data.
    Stores the photo + EC + pH the farmer captures.
    """
    __tablename__ = "daily_readings"

    id = Column(Integer, primary_key=True, index=True)
    bucket_id = Column(Integer, ForeignKey("experiments.id"))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    image_path = Column(String(255))
    ph = Column(Float)
    ec = Column(Float)
    water_temp = Column(Float)

    # Links to Lab Results (if taken)
    sample_bottle_label = Column(String(50), nullable=True)

    # Relationships
    experiment = relationship("Experiment", back_populates="readings")
    prediction = relationship("NPKPrediction", back_populates="daily_reading", uselist=False)

class LabResult(Base):
    """
    Answer Key: The 'Ground Truth' from the Lab.
    Linked to the physical Bottle Label.
    """
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True, index=True)
    sample_bottle_label = Column(String(50), unique=True, index=True) # e.g. "BucketA-Day5"

    n_val = Column(Float)
    p_val = Column(Float)
    k_val = Column(Float)

class NPKPrediction(Base):
    """
    AI Result: Stores the NPK values calculated by the CNN.
    """
    __tablename__ = "npk_predictions"

    id = Column(Integer, primary_key=True, index=True)
    daily_reading_id = Column(Integer, ForeignKey("daily_readings.id"))

    predicted_n = Column(Float)
    predicted_p = Column(Float)
    predicted_k = Column(Float)

    confidence_score = Column(Float, nullable=True)
    prediction_date = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    daily_reading = relationship("DailyReading", back_populates="prediction")
