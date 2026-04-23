import pytest
import models
import main

@pytest.fixture(autouse=True)
def reset_global_state():
    main.active_bucket_id = None
    yield
    main.active_bucket_id = None

def test_sensor_data_with_explicit_bucket(client, db_session):
    """
    Verifies that explicit bucket_id in payload is prioritized.
    """
    main.active_bucket_id = "Mix"
    payload = {
        "temperature": 25.0,
        "ec": 1.0,
        "ph": 6.0,
        "bucket_id": "NPK"
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    
    # Verify in DB using the transactional db_session
    reading = db_session.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.experiment.bucket_label == "NPK"

def test_sensor_data_with_global_fallback(client, db_session):
    """
    Verifies fallback to global active_bucket_id if missing in payload.
    """
    main.active_bucket_id = "Water"
    payload = {
        "temperature": 22.0,
        "ec": 1.2,
        "ph": 5.8
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    
    # Verify in DB
    reading = db_session.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.experiment.bucket_label == "Water"

def test_sensor_data_with_no_bucket(client, db_session):
    """
    Verifies bucket_label defaults if neither global nor payload provides it.
    """
    main.active_bucket_id = None
    payload = {
        "temperature": 20.0,
        "ec": 0.8,
        "ph": 7.0
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    
    # Verify in DB
    reading = db_session.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    # If no bucket provided, it should link to the default experiment created by iot_controller
    assert reading.experiment.bucket_label == "NPK"
