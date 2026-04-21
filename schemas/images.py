"""
Pydantic schemas and enums for image management and experiment tracking.
"""
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime, date

# --- Models & Enums ---
class BucketLabel(str, Enum):
    """Enumeration of valid agricultural bucket labels."""
    NPK = "NPK"
    Micro = "Micro"
    Mix = "Mix"
    Water = "Water"
    STOP = "STOP"

class ActiveBucketRequest(BaseModel):
    """Request schema for setting the active bucket."""
    bucket_id: BucketLabel

# --- Experiment Models ---
class ExperimentCreate(BaseModel):
    """Schema for creating a new agricultural experiment."""
    experiment_id: str = Field(..., example="EXP-101")
    bucket_label: Optional[str] = None
    start_date: Optional[date] = None

class ExperimentResponse(BaseModel):
    """Response schema for experiment metadata."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: Optional[str] = None
    bucket_label: Optional[str] = None
    start_date: Optional[date] = None

class ReadingHistoryItem(BaseModel):
    """Individual data point in an experiment's reading history."""
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    ph: float
    ec: float
    water_temp: float
    image_url: Optional[str] = None
    n: Optional[float] = None
    p: Optional[float] = None
    k: Optional[float] = None

class ExperimentHistoryResponse(BaseModel):
    """Response schema for an experiment's full reading history, grouped by bucket."""
    id: int
    experiment_id: Optional[str] = None
    history: Dict[str, List[ReadingHistoryItem]] # Grouped by bucket_label

# --- Auth Models ---
class LoginRequest(BaseModel):
    """Request schema for user authentication."""
    email: str
    password: str

class ImageInfo(BaseModel):
    """Metadata and status information for a single image."""
    filename: str
    reading_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    image_url: str
    is_orphaned: bool = False
    bucket_label: Optional[str] = None

class ActiveExperimentRequest(BaseModel):
    """Request schema for setting the currently active experiment."""
    experiment_id: Optional[str]

class PreFilterRequest(BaseModel):
    """Configuration parameters for the automated image pre-filtering process."""
    size_threshold: int = Field(default=1000, description="Minimum file size in bytes")
    green_threshold: float = Field(default=50.0, description="Minimum greenness percentage")

class RestoreRequest(BaseModel):
    """Request schema for restoring images from the trash."""
    log_ids: List[int] = Field(..., description="List of log IDs to restore from trash")

class TrashItemResponse(BaseModel):
    """Response schema for items currently in the automated trash."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    image_url: Optional[str] = None
    reason: str
    metric_value: Optional[float] = None
    timestamp: datetime
