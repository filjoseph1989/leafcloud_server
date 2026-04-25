from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TrashedCropResponse(BaseModel):
    id: int
    filename: str
    image_url: str
    metric_value: float
    timestamp: datetime
    is_viewed: bool
    action_type: str

    model_config = {
        "from_attributes": True
    }

class TrashScanResponse(BaseModel):
    image: Optional[TrashedCropResponse] = None
    remaining_count: int
    current_index: int
