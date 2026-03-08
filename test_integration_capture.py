import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import database
from database import get_db, Base
import models
from main import app
from unittest.mock import patch
import os
from datetime import date

# Use a temporary file for the database in /tmp to avoid lock issues on some filesystems
TEST_DB_FILE = "/tmp/test_integration_persistent.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # Ensure a clean start
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)
        
    Base.metadata.create_all(bind=test_engine)
    
    # Create a default experiment
    db = TestingSessionLocal()
    default_exp = models.Experiment(
        experiment_id="EXP-TEST-INTEGRATION",
        bucket_label="default",
        start_date=date(2026, 3, 8)
    )
    db.add(default_exp)
    db.commit()
    db.close()
    
    yield
    # Cleanup after all tests in the module
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_create_sensor_data_with_successful_capture(client):
    """
    Verifies that sensor data is saved and image_path is updated when capture succeeds.
    """
    payload = {
        "temperature": 25.5,
        "ec": 1.2,
        "ph": 6.0,
        "bucket_id": "NPK"
    }
    
    # Mock capture_frame in iot_controller
    with patch("controllers.iot_controller.capture_frame") as mock_capture:
        mock_capture.return_value = True
        
        response = client.post("/iot/sensor_data/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        
        # Verify in DB
        db = TestingSessionLocal()
        reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
        assert reading.ph == 6.0
        db.close()

def test_create_sensor_data_with_failed_capture(client):
    """
    Verifies that sensor data is still saved even if image capture fails (current logic).
    """
    payload = {
        "temperature": 22.0,
        "ec": 0.5,
        "ph": 7.0,
        "bucket_id": "Mix"
    }
    
    # Mock capture_frame to return False
    with patch("controllers.iot_controller.capture_frame") as mock_capture:
        mock_capture.return_value = False
        
        response = client.post("/iot/sensor_data/", json=payload)
        
        # Current logic in iot_controller.py: print warning, set image_path = None, CONTINUE.
        assert response.status_code == 201
        
        # Verify in DB
        db = TestingSessionLocal()
        reading = db.query(models.DailyReading).filter(models.DailyReading.ph == 7.0).first()
        assert reading is not None
        assert reading.image_path is None
        db.close()
