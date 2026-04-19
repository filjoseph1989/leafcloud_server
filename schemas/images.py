from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime, date

# --- Models & Enums ---
class BucketLabel(str, Enum):
    NPK = "NPK"
    Micro = "Micro"
    Mix = "Mix"
    Water = "Water"
    STOP = "STOP"

class ActiveBucketRequest(BaseModel):
    bucket_id: BucketLabel

# --- Experiment Models ---
class ExperimentCreate(BaseModel):
    experiment_id: str = Field(..., example="EXP-101")
    bucket_label: Optional[str] = None
    start_date: Optional[date] = None

class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_id: Optional[str] = None
    bucket_label: Optional[str] = None
    start_date: Optional[date] = None

class ReadingHistoryItem(BaseModel):
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
    id: int
    experiment_id: Optional[str] = None
    history: Dict[str, List[ReadingHistoryItem]] # Grouped by bucket_label

# --- Auth Models ---
class LoginRequest(BaseModel):
    email: str
    password: str

class ImageInfo(BaseModel):
    filename: str
    reading_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    image_url: str
    is_orphaned: bool = False
    bucket_label: Optional[str] = None

class ActiveExperimentRequest(BaseModel):
    experiment_id: Optional[str]

class PreFilterRequest(BaseModel):
    size_threshold: int = Field(default=1000, description="Minimum file size in bytes")
    green_threshold: float = Field(default=50.0, description="Minimum greenness percentage")

class RestoreRequest(BaseModel):
    log_ids: List[int] = Field(..., description="List of log IDs to restore from trash")
