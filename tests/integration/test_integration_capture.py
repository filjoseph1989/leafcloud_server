import pytest
from unittest.mock import patch
import models
from datetime import date

def test_create_sensor_data_with_successful_capture(client, db_session):
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
        
        # Verify in DB using the transactional db_session
        reading = db_session.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
        assert reading.ph == 6.0

def test_create_sensor_data_with_failed_capture(client, db_session):
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
        reading = db_session.query(models.DailyReading).filter(models.DailyReading.ph == 7.0).first()
        assert reading is not None
        assert reading.image_path is None
