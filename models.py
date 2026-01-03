from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class SensorData(Base):
    """
    Stores time-series data from environmental sensors (pH, EC, temperature).
    Linked by a device_id (e.g., 'bucket_1') and timestamp.
    """
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True)
    device_id = Column(String, index=True)

    ec = Column(Float)
    ph = Column(Float)
    temp_c = Column(Float)
    # ambient_temp = Column(Float, nullable=True) # From DHT22
    # ambient_humid = Column(Float, nullable=True) # From DHT22

class ImageData(Base):
    """
    Stores metadata for captured leaf images.
    The actual image is stored on disk/cloud, here we store the path/URL.
    """
    __tablename__ = "image_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True)
    device_id = Column(String, index=True)
    
    image_path = Column(String) # URL or file path
    
    # Relationship: One image can have one prediction (or many, but usually one active)
    predictions = relationship("NPKPrediction", back_populates="image")

class NPKPrediction(Base):
    """
    Stores NPK values predicted by the CNN model.
    Linked to the specific image it was derived from.
    """
    __tablename__ = "npk_predictions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True)
    
    # Foreign Key to ImageData
    image_id = Column(Integer, ForeignKey("image_data.id"))
    image = relationship("ImageData", back_populates="predictions")
    
    n_ppm = Column(Float)
    p_ppm = Column(Float)
    k_ppm = Column(Float)
    
    confidence = Column(Float, nullable=True) # Model confidence score

class GroundTruth(Base):
    """
    Stores the 'Actual' NPK values obtained from Laboratory Analysis.
    Crucial for training the regression model (Calibration/Validation).
    """
    __tablename__ = "ground_truth"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True) # Date of sample collection
    device_id = Column(String, index=True)   # Which bucket/setup
    
    n_actual = Column(Float)
    p_actual = Column(Float)
    k_actual = Column(Float)
    
    lab_report_ref = Column(String, nullable=True) # Optional: Reference to physical lab report ID
