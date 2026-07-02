from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TelemetryData(BaseModel):
    ph: float
    ec: float
    water_temp: float
    status: str

class NutrientEstimation(BaseModel):
    n_ppm: float
    p_ppm: float
    k_ppm: float
    total_estimated_ppm: float
    unit: str = "ppm"

class AdvisoryInsight(BaseModel):
    summary: str # e.g. "Optimal Balance" or "Nutrient Depletion"
    explanation: str # Detailed explanation of what the numbers mean
    farmer_action: str # Clear instructions on what to do next

class ActionableAlert(BaseModel):
    level: str # INFO, WARNING, CRITICAL
    message: str
    action_required: bool
    topup_macro_ml: float
    topup_micro_ml: float

class DashboardResponse(BaseModel):
    tank_id: int
    tank_name: str
    last_updated: datetime
    image_url: str
    health_status: str # e.g., HEALTHY, NUTRIENT DEFICIENT
    profile_detected: str # e.g., Macro-Leaning Blend
    predicted_class: str # e.g., Mix, NPK, Micro, Water
    is_anomaly: bool
    macro_scale: float
    micro_scale: float
    
    telemetry: TelemetryData
    estimated_nutrients: NutrientEstimation
    advisory: AdvisoryInsight
    alert: Optional[ActionableAlert] = None
