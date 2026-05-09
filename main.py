import os
import re
import platform
import socket
import threading
import time
import cv2

# --- WSL/FFMPEG Optimization (MUST BE AT TOP) ---
if "microsoft-standard-WSL2" in platform.uname().release or platform.system() == "Darwin":
    # We set multiple timeout variations to ensure FFmpeg picks one up
    # buffer_size: 10MB to prevent UDP packet loss
    # fifo_size: helps with jitter
    # loglevel;quiet: silences annoying initialization/sync warnings
    # protocol_whitelist: allows UDP and TCP streams
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "protocol_whitelist;file,rtp,udp,tcp|timeout;5000000|stimeout;5000000|buffer_size;10485760|fifo_size;500000|overrun_nonfatal;1|fflags;nobuffer|probesize;128000|analyzeduration;500000"
    
    # Debugging (optional, keeping for stability)
    if os.getenv("DEBUG_VIDEO"):
        os.environ["OPENCV_VIDEOIO_DEBUG"] = "1"
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "48"

def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_all_ips():
    """Returns all potential IPs for this host, prioritizing LAN IPs over WSL internal ones."""
    wsl_ip = get_host_ip()
    ips = []
    
    if "microsoft-standard-WSL2" in platform.uname().release:
        try:
            import subprocess
            output = subprocess.check_output(["ipconfig.exe"], stderr=subprocess.DEVNULL).decode()
            for line in output.splitlines():
                if "IPv4 Address" in line:
                    ip = line.split(":")[-1].strip()
                    # Prioritize common LAN ranges (192.168.x.x, 10.x.x.x)
                    if ip.startswith("192.168.") or ip.startswith("10."):
                        ips.append(ip)
                    elif ip != wsl_ip and not ip.startswith("127."):
                        ips.append(ip)
        except:
            pass
    
    if wsl_ip not in ips:
        ips.append(wsl_ip)
    return ips

from datetime import datetime, date
from urllib.parse import urlparse
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from fastapi import FastAPI, Form, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc
import numpy as np
from PIL import Image
from dotenv import load_dotenv
from passlib.context import CryptContext
import anyio
import image_filtering
import shutil
from contextlib import asynccontextmanager

from database import get_db, engine, Base
import models
from controllers.iot_controller import iot_router, init_iot_controller, resolve_experiment
from controllers.images_controller import images_router
from controllers.cropping_controller import cropping_router
from controllers.trash_controller import trash_router
from schemas.images import (
    BucketLabel, ActiveBucketRequest, ExperimentCreate, ExperimentResponse,
    ReadingHistoryItem, ExperimentHistoryResponse, LoginRequest, RegisterRequest, ImageInfo,
    ActiveExperimentRequest
)

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Global State ---
active_bucket_id: Optional[str] = None
active_experiment_id: Optional[str] = None
restart_requested: bool = False
ph_update_requested: bool = False
ec_calibration_requested: bool = False
ph_401_calibration_requested: bool = False
ph_686_calibration_requested: bool = False

# --- Video Management ---
class VideoManager:
    """
    Manages a single connection to the video stream and shares frames across the app.
    """
    def __init__(self):
        self.source_url = os.getenv("VIDEO_STREAM_URL", "udp://0.0.0.0:5000")
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.is_wsl = "microsoft-standard-WSL2" in platform.uname().release
        self.is_darwin = platform.system() == "Darwin"
        
        if self.is_wsl or self.is_darwin:
            # WSL/Darwin specific listener adjustments
            if "udp://" in self.source_url:
                if "?listen=1" not in self.source_url:
                    sep = "&" if "?" in self.source_url else "?"
                    self.source_url += f"{sep}listen=1"
                
                # fifo_size: helps with jitter
                # timeout: 5s for the initial open to keep the loop responsive
                if "fifo_size" not in self.source_url:
                    self.source_url += "&fifo_size=1000000&overrun_nonfatal=1&timeout=5000000"
            
            ips = get_all_ips()
            port = "5000"
            try: port = urlparse(self.source_url).port or "5000"
            except: pass
            
            label = "[WSL Server]" if self.is_wsl else "[Darwin Server]"
            print(f"📡 {label} Video Listener ACTIVATED on: {self.source_url}")
            print(f"📡 {label} Potential IPs to use in Pi command (try LAN first):")
            for ip in ips:
                print(f"   - {ip}:{port}")
            
            # Suggest the first IP (likely LAN if on WSL)
            primary_ip = ips[0]
            print(f"💡 PI COMMAND: rpicam-vid -t 0 --inline -g 30 --flush -o udp://{primary_ip}:{port}")
            if self.is_wsl:
                print(f"🛑 IMPORTANT: If it fails, check for other processes on port {port}: 'lsof -i :{port}'")
                print(f"💡 DEBUG TIP: Test connectivity with 'nc -ul {port}' (it should show garbled data if streaming).")

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()
            print(f"📹 Video Manager: Starting for {self.source_url}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None

    def _worker(self):
        port = "5000"
        try:
            parsed = urlparse(self.source_url)
            port = parsed.port or "5000"
        except: pass

        while self.running:
            # 1. Pre-check: Only if we are acting as a UDP server
            is_udp_listener = "udp://" in self.source_url and ("0.0.0.0" in self.source_url or "listen=1" in self.source_url)
            
            if is_udp_listener:
                print(f"⏳ Video Manager: Checking for incoming packets on UDP {port}...")
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", int(port)))
                    sock.settimeout(5.0)
                    data, addr = sock.recvfrom(1024)
                    print(f"📡 Video Manager: SUCCESS! Received {len(data)} bytes from {addr}. Data is arriving!")
                    sock.close()
                except socket.timeout:
                    print(f"⚠️ Video Manager: No UDP packets received on port {port} in 5s.")
                    print(f"   Check your Pi command, Windows Firewall, and WSL NAT routing.")
                    sock.close()
                    time.sleep(2.0)
                    continue
                except Exception as e:
                    print(f"⚠️ Video Manager: Port check failed: {e}")
                    sock.close()
                    time.sleep(5.0)
                    continue

            # 2. Open the stream with OpenCV
            print(f"⏳ Video Manager: Opening OpenCV capture for {self.source_url}...")
            cap = cv2.VideoCapture(self.source_url, cv2.CAP_FFMPEG)
            
            # Fallback 1: Try without forcing CAP_FFMPEG (some builds prefer auto-detection)
            if not cap.isOpened():
                cap = cv2.VideoCapture(self.source_url)
            
            # Fallback 2: Simple URL if the full one failed
            if not cap.isOpened() and "?" in self.source_url:
                simple_url = self.source_url.split("?")[0]
                print(f"⚠️ Video Manager: Retrying with simple URL: {simple_url}")
                cap = cv2.VideoCapture(simple_url, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(simple_url)
            
            if not cap.isOpened():
                print(f"⚠️ Video Manager: No stream detected yet. (Ensure Pi is sending to the correct IP).")
                time.sleep(2.0)
                continue

            print(f"✅ Video Manager: Connected to {self.source_url}")
            frame_count = 0
            while self.running:
                success, frame = cap.read()
                if success:
                    frame_count += 1
                    with self.lock:
                        self.latest_frame = frame.copy()
                    if frame_count % 100 == 0:
                        print(f"DEBUG: Video Manager received {frame_count} frames so far.")
                else:
                    print(f"⚠️ Video Manager: Lost stream from {self.source_url} after {frame_count} frames. Reconnecting...")
                    break

            cap.release()
            time.sleep(1.0)

    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is not None:
                h, w = self.latest_frame.shape[:2]
                print(f"DEBUG: VideoManager providing frame: {w}x{h}")
                return self.latest_frame.copy()
            else:
                print("DEBUG: VideoManager has NO frame to provide (latest_frame is None).")
        return None

video_manager = VideoManager()

# Load AI Brain (New Regression Model)
import os
os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
try:
    import tensorflow as tf
    # Load the new regression model
    model = tf.keras.models.load_model("leafcloud_regression_model.keras")
    print("🧠 AI Regression Model (NPK/Micro) loaded successfully.")
except Exception as e:
    print(f"⚠️ AI Model not found or failed to load: {e}. Using dummy predictions.")
    model = None

import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leafcloud")

# Initialize IoT Controller with dependencies
init_iot_controller(
    model=model,
    video_manager=video_manager,
    bucket_getter=lambda: active_bucket_id,
    experiment_getter=lambda: active_experiment_id,
    ph_update_getter=lambda: ph_update_requested
)

app = FastAPI(title="LEAFCLOUD API")

@app.middleware("http")
async def handle_stale_nfs(request: Request, call_next):
    try:
        return await call_next(request)
    except OSError as e:
        if e.errno == 70:  # Stale NFS file handle
            logger.warning("Stale NFS handle serving %s — drive may have remounted", request.url.path)
            return Response("File unavailable: storage device not ready", status_code=503)
        raise

_CROP_SUFFIX_RE = re.compile(r"_[a-f0-9]{6}\.jpg$")

@app.middleware("http")
async def redirect_misrouted_crops(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404 and request.url.path.startswith("/images/"):
        tail = request.url.path[len("/images/"):]
        if _CROP_SUFFIX_RE.search(tail):
            return RedirectResponse(url=f"/cropped_dataset/{tail}", status_code=301)
    return response

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the LEAFCLOUD Server API",
        "documentation": "/docs",
        "status": "online"
    }

# Register Routers
app.include_router(iot_router)
app.include_router(images_router)
app.include_router(cropping_router)
app.include_router(trash_router)

# Serve static images for the app
_base_dir = os.path.dirname(os.path.abspath(__file__))
_images_dir = os.path.join(_base_dir, "images")
_cropped_dir = os.path.join(_base_dir, "cropped_dataset")
_trash_dir = os.path.join(_cropped_dir, "temp_trash")
os.makedirs(_images_dir, exist_ok=True)
os.makedirs(_cropped_dir, exist_ok=True)
os.makedirs(_trash_dir, exist_ok=True)
app.mount("/images", StaticFiles(directory=_images_dir), name="images")
app.mount("/cropped_dataset", StaticFiles(directory=_cropped_dir), name="cropped_dataset")
app.mount("/temp_trash", StaticFiles(directory=_trash_dir), name="temp_trash")

# --- Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    video_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    video_manager.stop()

# --- 1. ENDPOINTS FOR CONTROL ---

@app.get("/control/current-status")
def get_current_status():
    """
    Returns the global active bucket and general system status.
    The Raspberry Pi polls this to know which bucket is active.
    """
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

from pydantic import BaseModel, Field, ConfigDict, AliasChoices, field_validator

class CalibrationType(str, Enum):
    EC = "ec"
    PH_401 = "ph_4.01"
    PH_686 = "ph_6.86"
    CLEAR = "clear"

class CalibrationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    calibration_type: CalibrationType = Field(..., validation_alias=AliasChoices("calibration_type", "type", "cal_type"))

    @field_validator("calibration_type", mode="before")
    @classmethod
    def validate_calibration_type(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        
        v_lower = v.lower().replace(" ", "_").replace("-", "_")
        
        # Mapping common variations
        mapping = {
            "ph401": "ph_4.01",
            "ph_401": "ph_4.01",
            "ph4.01": "ph_4.01",
            "ph686": "ph_6.86",
            "ph_686": "ph_6.86",
            "ph6.86": "ph_6.86",
            "ec": "ec",
            "clear": "clear"
        }
        return mapping.get(v_lower, v_lower)

@app.post("/control/request-calibration")
async def request_calibration(request: Request):
    """
    Sets the global calibration request flags.
    Handles various payload formats from the Mobile App.
    """
    global ec_calibration_requested, ph_401_calibration_requested, ph_686_calibration_requested
    
    body_bytes = await request.body()
    body_str = body_bytes.decode()
    
    try:
        data = await request.json()
    except Exception:
        logger.error(f"❌ Failed to parse JSON from body: {body_str}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"📥 Received Calibration Request: {data}")

    # Try to parse with the model to use the mapping/aliases
    try:
        cal_req = CalibrationRequest.model_validate(data)
        cal_type = cal_req.calibration_type
    except Exception as e:
        logger.warning(f"⚠️ Model validation failed, trying manual fallback: {e}")
        # Manual fallback if model fails
        cal_type_raw = data.get("calibration_type") or data.get("type") or data.get("cal_type")
        if not cal_type_raw:
            logger.error(f"❌ Missing calibration type in payload: {data}")
            return JSONResponse(status_code=422, content={"detail": "Missing calibration type", "received": data})
        
        # Simple manual normalization
        cal_type = str(cal_type_raw).lower().replace(" ", "_")
        if "4.01" in cal_type or "401" in cal_type:
            cal_type = CalibrationType.PH_401
        elif "6.86" in cal_type or "686" in cal_type:
            cal_type = CalibrationType.PH_686
        elif "ec" in cal_type:
            cal_type = CalibrationType.EC
        else:
            cal_type = CalibrationType.CLEAR

    # Reset all first
    ec_calibration_requested = False
    ph_401_calibration_requested = False
    ph_686_calibration_requested = False

    if cal_type == CalibrationType.EC:
        ec_calibration_requested = True
    elif cal_type == CalibrationType.PH_401:
        ph_401_calibration_requested = True
    elif cal_type == CalibrationType.PH_686:
        ph_686_calibration_requested = True
    
    print(f"🧪 Calibration set to: {cal_type}")
    return {
        "status": "success", 
        "calibration_type": cal_type,
        "ec_calibration_requested": ec_calibration_requested,
        "ph_401_calibration_requested": ph_401_calibration_requested,
        "ph_686_calibration_requested": ph_686_calibration_requested
    }

@app.post("/control/acknowledge-calibration")
def acknowledge_calibration():
    """
    Clears all global calibration request flags.
    Called by the IoT device once calibration is complete.
    """
    global ec_calibration_requested, ph_401_calibration_requested, ph_686_calibration_requested
    ec_calibration_requested = False
    ph_401_calibration_requested = False
    ph_686_calibration_requested = False
    print("✅ Calibration acknowledged by IoT device. Flags reset.")
    return {"status": "success", "message": "All calibration flags reset"}

@app.post("/control/request-ph-update")
def request_ph_update():
    """
    Sets the global pH update request flag.
    Called by the Mobile App.
    """
    global ph_update_requested
    ph_update_requested = True
    print("🔔 pH update requested by mobile app. Stopping VideoManager.")
    video_manager.stop()
    return {"status": "success", "ph_update_requested": True}

@app.post("/control/acknowledge-ph-update")
def acknowledge_ph_update():
    """
    Clears the global pH update request flag.
    Called by the IoT device.
    """
    global ph_update_requested
    ph_update_requested = False
    print("✅ pH update acknowledged by IoT device. Flag reset. Restarting VideoManager.")
    video_manager.start()
    return {"status": "success", "ph_update_requested": False}

@app.post("/control/restart-iot")
def restart_iot():
    """
    Sets the global restart flag and restarts the VideoManager.
    Called by the Mobile App.
    """
    global restart_requested
    restart_requested = True
    print("⚠️ Restart requested by mobile app. Resetting VideoManager...")
    video_manager.stop()
    video_manager.start()
    return {"status": "success", "restart_requested": True}

@app.post("/control/acknowledge-restart")
def acknowledge_restart():
    """
    Clears the global restart flag.
    Called by the IoT device.
    """
    global restart_requested
    restart_requested = False
    print("✅ Restart acknowledged by IoT device. Flag reset.")
    return {"status": "success", "restart_requested": False}

@app.post("/control/active-experiment")
def set_active_experiment(request: ActiveExperimentRequest):
    """
    Updates the global active experiment ID.
    Called by the Mobile App when the user starts a new crop cycle.
    """
    global active_experiment_id
    active_experiment_id = request.experiment_id
    return {"status": "success", "active_experiment_id": active_experiment_id}

@app.post("/control/active-bucket")
def set_active_bucket(request: ActiveBucketRequest, db: Session = Depends(get_db)):
    """
    Updates the global active bucket ID and ensures a corresponding experiment exists.
    """
    global active_bucket_id, active_experiment_id

    # Log request to file for easier debugging
    with open("logs/control_requests.log", "a") as f:
        f.write(f"{datetime.now()} - Received active bucket request: {request.bucket_id}\n")

    if request.bucket_id == BucketLabel.STOP:
        active_bucket_id = None
        active_experiment_id = None
        return {
            "status": "success",
            "active_bucket_id": None,
            "message": "System stopped"
        }
    
    # 1. Update in-memory state
    active_bucket_id = request.bucket_id.value

    # 2. Ensure an experiment exists for this bucket (Auto-Initialization)
    experiment = resolve_experiment(db, bucket_label=active_bucket_id)
    
    # 3. Update global active_experiment_id string
    active_experiment_id = experiment.experiment_id

    return {
        "status": "success",
        "active_bucket_id": active_bucket_id,
        "experiment_id": active_experiment_id,
        "message": f"Active bucket set to {active_bucket_id}, linked to experiment {active_experiment_id}"
    }

@app.post("/auth/register", status_code=201)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = pwd_context.hash(request.password)
    user = models.User(name=request.name, email=request.email, hashed_password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": "Account created successfully",
        "user": {"id": user.id, "name": user.name, "email": user.email}
    }

@app.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == request.email).first()

    if not user or not pwd_context.verify(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "status": "success",
        "token": "demo-access-token-xyz-789",
        "message": "Login successful",
        "user": {"id": user.id, "name": user.name, "email": user.email}
    }

@app.get("/test")
def test_connection():
    return {"status": "success", "message": "Server is reachable via this address"}

# --- 2. ENDPOINTS FOR EXPERIMENTS ---

@app.post("/experiments/", response_model=ExperimentResponse, status_code=201)
def create_experiment(experiment: ExperimentCreate, db: Session = Depends(get_db)):
    """
    Creates a new experiment.
    """
    db_experiment = db.query(models.Experiment).filter(models.Experiment.experiment_id == experiment.experiment_id).first()
    if db_experiment:
        raise HTTPException(status_code=400, detail="Experiment ID already exists")

    new_exp = models.Experiment(
        experiment_id=experiment.experiment_id,
        bucket_label=experiment.bucket_label,
        start_date=experiment.start_date
    )
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    return new_exp

@app.get("/experiments/", response_model=list[ExperimentResponse])
def list_experiments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Returns a list of all experiments.
    """
    experiments = db.query(models.Experiment).offset(skip).limit(limit).all()
    return experiments

@app.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    """
    Retrieves details of a specific experiment by its internal ID.
    """
    experiment = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment

@app.get("/experiments/{experiment_id}/history", response_model=ExperimentHistoryResponse, response_model_exclude_none=True)
def get_experiment_history(experiment_id: int, db: Session = Depends(get_db)):
    """
    Returns time-series sensor data and AI predictions for a specific experiment, grouped by bucket.
    """
    experiment = db.query(models.Experiment).filter(models.Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Query with eager loading of prediction
    readings = db.query(models.DailyReading)\
        .filter(models.DailyReading.experiment_id == experiment_id)\
        .order_by(models.DailyReading.timestamp.asc())\
        .all()

    # Group by bucket_label and extract NPK
    # Note: All readings in this query belong to the same experiment, 
    # and thus the same bucket_label from the Experiment table.
    label = experiment.bucket_label or "unknown"
    history_list = []
    
    for r in readings:
        # Manually construct item to handle the nested prediction relationship
        item = {
            "timestamp": r.timestamp,
            "ph": r.ph,
            "ec": r.ec,
            "water_temp": r.water_temp,
            "image_url": f"/{r.image_path.replace(chr(92), '/')}" if r.image_path else None,
            "n": r.prediction.predicted_n if r.prediction else None,
            "p": r.prediction.predicted_p if r.prediction else None,
            "k": r.prediction.predicted_k if r.prediction else None,
        }
        history_list.append(item)

    return {
        "id": experiment.id,
        "experiment_id": experiment.experiment_id,
        "history": {label: history_list}
    }

def generate_classification(n, p, k, ph, ec):
    if ph < 5.5 or ph > 7.0:
        return "pH Lockout"
    if ec > 2.8:
        return "Over-Dosed"
    if ec < 0.6:
        return "Under-Dosed"
    if n < 150 or p < 250 or k < 400:
        return "Macro-Deficiency"
    return "Optimal"

def generate_recommendation(n, p, k, ph, ec):
    """
    Rule-based engine to convert sensor/AI data into actionable advice.
    """
    # Priority 1: pH Lockout (Critical)
    if ph < 5.5 or ph > 7.0:
        return f"pH is {ph:.2f} (Out of Range). Adjust to 5.8-6.5 immediately to prevent nutrient lockout."

    # Priority 2: General Solution Strength (EC)
    if ec < 0.6:
        return "Nutrient solution is too diluted (EC < 0.6). Add balanced fertilizer."
    if ec > 2.8:
        return "Nutrient burn risk (EC > 2.8). Dilute with fresh water immediately."

    # Priority 3: Specific Nutrient Deficiencies (Calculated from Regression Model)
    # Thresholds set at ~50% of 2ml/L target (Target N: 160-320, P: 300-600, K: 300-1020)
    if n < 150:
        return f"Nitrogen level is low ({n:.1f} ppm). Supplement with Nitrogen source."
    if p < 250:
        return f"Phosphorus deficiency suspected ({p:.1f} ppm). Adjust nutrient balance."
    if k < 400:
        return f"Potassium level is below optimal ({k:.1f} ppm). Monitor for leaf yellowing."

    # Priority 4: Optimal
    return "Plant health is optimal. Nutrient concentrations are within the target range for the current growth stage."

@app.get("/video_feed/")
@app.get("/video_feed")
async def video_feed():
    """
    Proxies MJPEG stream from the shared VideoManager to the client.
    """
    def generate():
        print(f"📹 Client connected to shared video_feed.")
        frame_count = 0

        while True:
            frame = video_manager.get_latest_frame()

            if frame is None:
                # Fallback: Generate a "NO SIGNAL" placeholder if stream is missing
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, "NO SIGNAL", (220, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(frame, "Waiting for stream...", (10, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                # Encode and yield placeholder
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                      b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

                # Sleep briefly to avoid high CPU usage while waiting
                time.sleep(1.0)
            else:
                # Success occasionally log
                if frame_count % 300 == 0:
                    h, w, _ = frame.shape
                    print(f"✅ Serving video frame #{frame_count} ({w}x{h}) from shared VideoManager")
                frame_count += 1

                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    continue

                yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

            # Control frame rate for clients
            time.sleep(0.04) # ~25 FPS

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

# --- 3. ENDPOINT FOR MOBILE APP (Android uses this) ---
@app.get("/app/latest_status/")
def get_dashboard_data(request: Request, db: Session = Depends(get_db)):
    # Sort by the DailyReading ID to get the absolute last record added to the DB
    latest = db.query(models.NPKPrediction)\
        .join(models.DailyReading)\
        .order_by(desc(models.DailyReading.id))\
        .first()

    if not latest:
        return {"error": "No data available yet"}

    # Get the sensor data linked to this prediction
    # Accessing via relationship
    reading = latest.daily_reading

    # Generate actionable advice
    recommendation = generate_recommendation(
        latest.predicted_n,
        latest.predicted_p,
        latest.predicted_k,
        reading.ph,
        reading.ec
    )

    classification = generate_classification(
        latest.predicted_n,
        latest.predicted_p,
        latest.predicted_k,
        reading.ph,
        reading.ec
    )

    # Build the full image URL
    image_url = None
    if reading.image_path:
        base_url = str(request.base_url).rstrip("/")
        # Path in DB is "images/2026-05-08/..."
        # Mount is "/images" pointing to the "images" folder.
        # So we need the URL to be: base_url + "/images/2026-05-08/..."
        # BUT wait, the StaticFiles mount maps the URL prefix to the DIRECTORY content.
        # If /images maps to the 'images' folder, then:
        # http://host/images/foo.jpg -> images/foo.jpg
        # If image_path is "images/2026-05-08/foo.jpg", then we just prepend base_url.
        
        path_suffix = reading.image_path.replace("\\", "/")
        
        # If the path already starts with 'images/', we just join it with the base_url
        if path_suffix.startswith("images/"):
            image_url = f"{base_url}/{path_suffix}"
        else:
            # Fallback just in case
            image_url = f"{base_url}/images/{path_suffix}"

    return {
        "timestamp": latest.prediction_date,
        "image_url": image_url,
        "sensors": {
            "ec": reading.ec,
            "ph": reading.ph,
            "temp_c": reading.water_temp
        },
        "predictions": {
            "n": latest.predicted_n,
            "p": latest.predicted_p,
            "k": latest.predicted_k
        },
        "status": {
            "overall_status": classification,
            "classification": classification
        },
        "recommendation": recommendation
    }

@app.get("/app/history/")
def get_history(limit: int = 30, db: Session = Depends(get_db)):
    """
    Retrieves historical data for charts.
    Returns the last 'limit' readings, ordered chronologically.
    """
    # Join DailyReading (Sensors) with NPKPrediction (AI)
    # We select records that have both sensor data and a prediction
    history = db.query(models.DailyReading, models.NPKPrediction)\
        .join(models.NPKPrediction, models.DailyReading.id == models.NPKPrediction.daily_reading_id)\
        .order_by(models.DailyReading.timestamp.desc())\
        .limit(limit)\
        .all()

    # The query returns a list of tuples: (DailyReading, NPKPrediction)
    # We need to reverse it to be chronological (oldest -> newest) for charts
    history = history[::-1]

    response_data = []
    for reading, prediction in history:
        response_data.append({
            "timestamp": reading.timestamp,
            "ph": reading.ph,
            "ec": reading.ec,
            "temp": reading.water_temp,
            "n_ppm": prediction.predicted_n,
            "p_ppm": prediction.predicted_p,
            "k_ppm": prediction.predicted_k
        })

    return response_data

@app.get("/app/alerts/")
def get_alerts(limit: int = 50, db: Session = Depends(get_db)):
    """
    Retrieves a list of proactive alerts based on historical data.
    Used to populate the 'Notifications' screen in the app.
    """
    # 1. Fetch recent history
    history = db.query(models.DailyReading, models.NPKPrediction)\
        .join(models.NPKPrediction, models.DailyReading.id == models.NPKPrediction.daily_reading_id)\
        .order_by(models.DailyReading.timestamp.desc())\
        .limit(limit)\
        .all()

    alerts = []

    # 2. Scan for issues
    for reading, prediction in history:
        # Check pH (Critical)
        if reading.ph < 5.5 or reading.ph > 7.0:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "critical",
                "message": f"pH Lockout detected ({reading.ph}). Nutrients unavailable."
            })

        # Check EC (Warning)
        if reading.ec < 0.8:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": f"Nutrient solution too weak (EC {reading.ec})."
            })
        elif reading.ec > 2.5:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "critical",
                "message": f"Nutrient burn risk! EC is extremely high ({reading.ec})."
            })

        # Check NPK (Deficiencies)
        if prediction.predicted_n < 100:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": "Nitrogen level is low."
            })
        if prediction.predicted_p < 30:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": "Phosphorus deficiency likely."
            })
        if prediction.predicted_k < 150:
            alerts.append({
                "timestamp": reading.timestamp,
                "severity": "warning",
                "message": "Potassium level is below optimal."
            })

    return alerts

@app.get("/admin/readings/")
def list_readings(
    skip: int = 0,
    limit: int = 100,
    bucket_label: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to view raw daily readings.
    Useful for auditing data and verifying sensor inputs.
    """
    query = db.query(models.DailyReading)

    if bucket_label:
        query = query.join(models.Experiment).filter(models.Experiment.bucket_label == bucket_label)

    # Get total count for pagination UI
    total_count = query.count()

    readings = query.order_by(desc(models.DailyReading.timestamp))\
                    .offset(skip)\
                    .limit(limit)\
                    .all()

    return readings

if __name__ == "__main__":
    import uvicorn
    host_ip = get_host_ip()
    print(f"\n🚀 LEAFCLOUD SERVER STARTING...")
    print(f"🔗 Local Access: http://localhost:8000")
    print(f"🔗 Network Access: http://{host_ip}:8000")
    print(f"🎬 Video Feed: http://{host_ip}:8000/video_feed/\n")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
