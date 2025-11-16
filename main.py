import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from enum import Enum
from typing import List
from datetime import datetime

# --- 1. Pydantic Models (Data Schemas) ---
# These models define the *exact* structure of your JSON responses.
# FastAPI uses them to validate your data and auto-generate documentation.

# Sub-model for 'sensors' in latest_response.json
class SensorData(BaseModel):
    ec: float
    ph: float
    temp_c: float

# Sub-model for 'predictions' in latest_response.json
class PredictionData(BaseModel):
    n_ppm: float
    p_ppm: float
    k_ppm: float

# Define allowed status values using an Enum for robustness
class NutrientStatus(str, Enum):
    ok = "ok"
    low = "low"
    high = "high"

class OverallStatus(str, Enum):
    ok = "ok"
    warning = "warning"
    danger = "danger"

# Sub-model for 'status' in latest_response.json
class StatusData(BaseModel):
    n_status: NutrientStatus
    p_status: NutrientStatus
    k_status: NutrientStatus
    overall_status: OverallStatus

# Main model for latest_response.json
class LatestReadingResponse(BaseModel):
    timestamp: datetime
    plant_id: str
    lettuce_image_url: str
    sensors: SensorData
    predictions: PredictionData
    status: StatusData
    recommendation: str

# Model for one data point in history_response.json
class HistoryDataPoint(BaseModel):
    timestamp: datetime
    n_ppm: float
    p_ppm: float
    k_ppm: float
    ec: float
    ph: float

# Main model for history_response.json
class HistoryResponse(BaseModel):
    query_range: str
    data_points: List[HistoryDataPoint]

# --- 2. FastAPI App Instance ---
app = FastAPI(
    title="LEAFCLOUD API",
    description="API for the LEAFCLOUD Hydroponics Monitoring System.",
    version="1.0.0"
)

# --- 3. API Endpoints ---
@app.get(
    "/api/v1/readings/latest",
    response_model=LatestReadingResponse,
    summary="Get Latest Sensor Reading"
)

async def get_latest_reading():
    """
    Retrieves the single most recent reading from the hydroponics system.
    This provides all data needed for the main dashboard.
    """
    # --- This is your "dummy" data ---
    # In the future, you will replace this by fetching data
    # from your database (e.g., Firestore or PostgreSQL).
    dummy_data = {
      "timestamp": "2025-11-16T10:30:01Z",
      "plant_id": "bucket_1_lettuce",
      "lettuce_image_url": "https://placehold.co/600x400/5B9C4A/FFFFFF?text=Lettuce+Leaf\n(img_12345.jpg)",
      "sensors": {
        "ec": 790.5,
        "ph": 6.4,
        "temp_c": 25.1
      },
      "predictions": {
        "n_ppm": 139.4,
        "p_ppm": 46.5,
        "k_ppm": 185.8
      },
      "status": {
        "n_status": "low",
        "p_status": "ok",
        "k_status": "ok",
        "overall_status": "warning"
      },
      "recommendation": "Nitrogen is low. Consider adding 10ml of 'Grow' solution."
    }
    return dummy_data

@app.get(
    "/api/v1/readings/history",
    response_model=HistoryResponse,
    summary="Get Historical Sensor Readings"
)
async def get_history(range: str = "7d"):
    """
    Retrieves a list of historical readings for a specified time range.
    Used to populate charts in the app.
    
    Query Parameters:
    - **range**: The time range (e.g., '24h', '7d', '30d').
    """
    # --- This is your "dummy" data ---
    # In the future, you will query your database based on the 'range'
    dummy_data = {
      "query_range": range, # Use the 'range' parameter from the URL
      "data_points": [
        {
          "timestamp": "2025-11-16T10:30:00Z",
          "n_ppm": 139.4,
          "p_ppm": 46.5,
          "k_ppm": 185.8,
          "ec": 790.5,
          "ph": 6.4
        },
        {
          "timestamp": "2025-11-16T09:30:00Z",
          "n_ppm": 141.2,
          "p_ppm": 47.1,
          "k_ppm": 187.1,
          "ec": 800.0,
          "ph": 6.3
        },
        {
          "timestamp": "2025-11-16T08:30:00Z",
          "n_ppm": 142.1,
          "p_ppm": 47.2,
          "k_ppm": 188.0,
          "ec": 805.0,
          "ph": 6.3
        },
        {
          "timestamp": "2025-11-16T07:30:00Z",
          "n_ppm": 145.0,
          "p_ppm": 48.0,
          "k_ppm": 190.0,
          "ec": 810.0,
          "ph": 6.2
        }
      ]
    }
    return dummy_data

# This is for running the file directly
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)