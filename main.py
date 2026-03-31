import os
import platform

# --- WSL/FFMPEG Optimization ---
if "microsoft-standard-WSL2" in platform.uname().release:
    # protocol_whitelist: allows UDP stream
    # stimeout: timeout in microseconds (5s)
    # probesize/analyzeduration: help sync the stream faster
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "protocol_whitelist;file,rtp,udp|stimeout;5000000|fflags;nobuffer|probesize;128000|analyzeduration;500000"

def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't actually connect, just probes the local IP used for outbound
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

from datetime import datetime, date
from fastapi import FastAPI, Form, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
import cv2
from PIL import Image
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import socket
import threading
import time
from urllib.parse import urlparse
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from database import get_db, engine, Base
import models
from controllers.iot_controller import iot_router, init_iot_controller, resolve_experiment

load_dotenv()

# --- Global State ---
active_bucket_id: Optional[str] = None
active_experiment_id: Optional[str] = None
restart_requested: bool = False
ph_update_requested: bool = False
ec_calibration_requested: bool = False
ph_401_calibration_requested: bool = False
ph_686_calibration_requested: bool = False

# --- Video Management (Original Stable Version) ---
class VideoManager:
    def __init__(self):
        self.source_url = os.getenv("VIDEO_STREAM_URL", "udp://0.0.0.0:5000")
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.is_wsl = "microsoft-standard-WSL2" in platform.uname().release
        
        if self.is_wsl:
            if "udp://" in self.source_url and "0.0.0.0" in self.source_url:
                if "?listen" not in self.source_url:
                    self.source_url += "?listen=1"
            
            host_ip = get_host_ip()
            port = "5000"
            try: port = urlparse(self.source_url).port or "5000"
            except: pass
            
            print(f"📡 [WSL Server] Video Listener RE-ACTIVATED on: {self.source_url}")
            print(f"📡 [WSL Server] Send your camera stream to: {host_ip}:{port}")
            print(f"💡 PI COMMAND: ffmpeg -i /dev/video0 -f mpegts -codec:v mpeg1video -b:v 800k -r 30 udp://{host_ip}:{port}")

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None

    def _worker(self):
        # Extract port for error messages
        port = "5000"
        try:
            parsed = urlparse(self.source_url)
            port = parsed.port or "5000"
        except: pass

        while self.running:
            cap = cv2.VideoCapture(self.source_url)
            if not cap.isOpened():
                print(f"❌ Video Manager: Could not open {self.source_url}.")
                print(f"   1. Check if the Raspberry Pi is actually streaming.")
                print(f"   2. Ensure Windows Firewall allows UDP port {port}.")
                print(f"   3. Verify the Pi is sending to your Windows IP (run 'ipconfig').")
                time.sleep(2.0)
                continue

            print(f"✅ Video Manager: Connected to {self.source_url}")
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            first_frame = True

            while self.running:
                success, frame = cap.read()
                if success:
                    if first_frame:
                        print("🎬 Video Manager: Receiving frames!")
                        first_frame = False
                    with self.lock:
                        self.latest_frame = frame.copy()
                else:
                    print(f"⚠️ Video Manager: Stream interrupted. Retrying...")
                    break
            cap.release()
            time.sleep(1.0)

    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
        return None

video_manager = VideoManager()

# --- Models & Enums ---
class BucketLabel(str, Enum):
    NPK = "NPK"
    Micro = "Micro"
    Mix = "Mix"
    Water = "Water"
    STOP = "STOP"

class ActiveBucketRequest(BaseModel):
    bucket_id: BucketLabel

class ExperimentCreate(BaseModel):
    experiment_id: str = Field(..., json_schema_extra={"example": "EXP-101"})
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
    history: dict[str, list[ReadingHistoryItem]]

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

# AI Model (Disabled for speed)
model = None

init_iot_controller(
    model=model,
    video_manager=video_manager,
    bucket_getter=lambda: active_bucket_id,
    experiment_getter=lambda: active_experiment_id,
    ph_update_getter=lambda: ph_update_requested
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    video_manager.start()
    yield
    video_manager.stop()

app = FastAPI(title="LEAFCLOUD API", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "online", "message": "LeafCloud Server is reachable"}

app.include_router(iot_router)
os.makedirs("images", exist_ok=True)
app.mount("/images", StaticFiles(directory="images"), name="images")

@app.get("/control/current-status")
def get_current_status():
    return {
        "active_bucket_id": active_bucket_id,
        "active_experiment_id": active_experiment_id,
        "restart_requested": restart_requested,
        "ph_update_requested": ph_update_requested,
        "ec_calibration_requested": ec_calibration_requested,
        "ph_401_calibration_requested": ph_401_calibration_requested,
        "ph_686_calibration_requested": ph_686_calibration_requested,
        "server_time": datetime.now().isoformat()
    }

class CalibrationType(str, Enum):
    EC = "ec"
    PH_401 = "ph_401"
    PH_686 = "ph_686"
    STOP = "stop"

class CalibrationRequest(BaseModel):
    type: CalibrationType

@app.post("/control/request-calibration")
def request_calibration(request: CalibrationRequest):
    global ec_calibration_requested, ph_401_calibration_requested, ph_686_calibration_requested, ph_update_requested
    ec_calibration_requested = False
    ph_401_calibration_requested = False
    ph_686_calibration_requested = False
    ph_update_requested = False
    if request.type == CalibrationType.EC:
        ec_calibration_requested = True
    elif request.type == CalibrationType.PH_401:
        ph_401_calibration_requested = True
    elif request.type == CalibrationType.PH_686:
        ph_686_calibration_requested = True
    
    if request.type != CalibrationType.STOP:
        video_manager.stop()
    else:
        video_manager.start()
    return {"status": "success"}

@app.post("/control/acknowledge-calibration")
def acknowledge_calibration(request: CalibrationRequest):
    global ec_calibration_requested, ph_401_calibration_requested, ph_686_calibration_requested
    if request.type == CalibrationType.EC:
        ec_calibration_requested = False
    elif request.type == CalibrationType.PH_401:
        ph_401_calibration_requested = False
    elif request.type == CalibrationType.PH_686:
        ph_686_calibration_requested = False
    video_manager.start()
    return {"status": "success"}

@app.post("/control/request-ph-update")
def request_ph_update():
    global ph_update_requested
    ph_update_requested = True
    video_manager.stop()
    return {"status": "success"}

@app.post("/control/acknowledge-ph-update")
def acknowledge_ph_update():
    global ph_update_requested
    ph_update_requested = False
    video_manager.start()
    return {"status": "success"}

@app.post("/control/restart-iot")
def restart_iot():
    global restart_requested
    restart_requested = True
    video_manager.stop()
    video_manager.start()
    return {"status": "success"}

@app.post("/control/acknowledge-restart")
def acknowledge_restart():
    global restart_requested
    restart_requested = False
    return {"status": "success"}

@app.post("/control/active-bucket")
def set_active_bucket(request: ActiveBucketRequest, db: Session = Depends(get_db)):
    global active_bucket_id, active_experiment_id
    if request.bucket_id == BucketLabel.STOP:
        active_bucket_id = None
        active_experiment_id = None
        return {"status": "success", "message": "Stopped"}
    active_bucket_id = request.bucket_id.value
    experiment = resolve_experiment(db, bucket_label=active_bucket_id)
    active_experiment_id = experiment.experiment_id
    return {"status": "success", "active_bucket_id": active_bucket_id}

@app.post("/auth/login")
def login(request: LoginRequest):
    if request.email == "admin@leafcloud.com" and request.password == "admin":
        return {"status": "success", "token": "demo-access-token-xyz-789"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/video_feed")
async def video_feed():
    def generate():
        while True:
            frame = video_manager.get_latest_frame()
            if frame is None:
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, "NO SIGNAL", (220, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(1.0)
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret: continue
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.04)
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/app/latest_status/")
def get_dashboard_data(db: Session = Depends(get_db)):
    latest = db.query(models.NPKPrediction).join(models.DailyReading).order_by(desc(models.NPKPrediction.prediction_date)).first()
    if not latest: return {"error": "No data available yet"}
    reading = latest.daily_reading
    return {
        "timestamp": latest.prediction_date,
        "sensors": {"ph": reading.ph, "ec": reading.ec, "temp": reading.water_temp},
        "npk_levels": {"Nitrogen": latest.predicted_n, "Phosphorus": latest.predicted_p, "Potassium": latest.predicted_k}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
