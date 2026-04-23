from pydantic import BaseModel
from typing import Optional

class CropRequest(BaseModel):
    """Payload sent from Flutter when a user saves a crop."""
    rel_path: str
    center_x: float
    center_y: float
    display_width: float
    display_height: float

class SkipRequest(BaseModel):
    """Payload to skip an image."""
    rel_path: str

class CropNextResponse(BaseModel):
    """Data sent to mobile to display the next image."""
    rel_path: str
    image_url: str
