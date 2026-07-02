from fastapi import APIRouter
from app.api.v1.endpoints import auth, tank_configs, iot, calibration

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tank_configs.router, prefix="/tank-configs", tags=["tank-configs"])
api_router.include_router(iot.router, prefix="/iot", tags=["iot"])
api_router.include_router(calibration.router, prefix="/calibration", tags=["calibration"])
