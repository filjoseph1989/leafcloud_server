import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app
from unittest.mock import patch, MagicMock
import os

# Use a persistent SQLite file for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_integration.db"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Setup test DB
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
    models.Base.metadata.create_all(bind=test_engine)
    yield
    models.Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test_integration.db"):
        os.remove("./test_integration.db")

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
    
    # Mock capture_frame to return True
    with patch("main.capture_frame") as mock_capture:
        mock_capture.return_value = True
        
        response = client.post("/iot/sensor_data/", json=payload)
        if response.status_code == 422:
            print(response.json())
        assert response.status_code == 201
        data = response.json()
        assert "image_path" in data
        assert data["image_path"] is not None
        
        # Verify in DB
        db = TestingSessionLocal()
        reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
        assert reading.image_path is not None
        assert reading.ph == 6.0
        db.close()

def test_create_sensor_data_with_failed_capture(client):
    """
    Verifies that sensor data is NOT saved if image capture fails.
    """
    payload = {
        "temperature": 22.0,
        "ec": 0.5,
        "ph": 7.0,
        "bucket_id": "Mix"
    }
    
    # Mock capture_frame to return False
    with patch("main.capture_frame") as mock_capture:
        mock_capture.return_value = False
        
        # We expect a 500 error or similar if we strictly require the image
        response = client.post("/iot/sensor_data/", json=payload)
        
        assert response.status_code == 500
        assert "Capture failed" in response.json()["detail"]
        
        # Verify NOT in DB (the last reading should NOT be this one)
        db = TestingSessionLocal()
        reading = db.query(models.DailyReading).filter(models.DailyReading.ph == 7.0).first()
        assert reading is None
        db.close()
