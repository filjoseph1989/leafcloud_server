import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import models
from datetime import datetime

def test_update_ph_fifo_logic(client: TestClient, db_session: Session):
    """
    Test that the POST /iot/experiments/{experiment_id}/update-ph endpoint
    correctly updates the oldest pending reading for the experiment.
    """
    # 1. Setup: Create an experiment and three readings
    experiment = models.Experiment(experiment_id="EXP-TEST-01")
    db_session.add(experiment)
    db_session.commit()
    db_session.refresh(experiment)

    # Reading 1: Oldest
    reading1 = models.DailyReading(
        experiment_id=experiment.id,
        ph=5.0,
        ph_is_estimated=True,
        needs_ph_update=True,
        timestamp=datetime(2026, 3, 14, 10, 0, 0)
    )
    # Reading 2: Middle
    reading2 = models.DailyReading(
        experiment_id=experiment.id,
        ph=5.1,
        ph_is_estimated=True,
        needs_ph_update=True,
        timestamp=datetime(2026, 3, 14, 11, 0, 0)
    )
    # Reading 3: Not needing update
    reading3 = models.DailyReading(
        experiment_id=experiment.id,
        ph=6.0,
        ph_is_estimated=False,
        needs_ph_update=False,
        timestamp=datetime(2026, 3, 14, 12, 0, 0)
    )
    
    db_session.add_all([reading1, reading2, reading3])
    db_session.commit()

    # 2. Act: Update the first one
    payload = {"ph": 6.5}
    response = client.post(f"/iot/experiments/EXP-TEST-01/update-ph", json=payload)
    
    # 3. Assert
    assert response.status_code == 200
    data = response.json()
    assert data["updated_reading_id"] == reading1.id
    assert data["new_ph"] == 6.5

    # Verify in DB
    db_session.refresh(reading1)
    assert reading1.ph == 6.5
    assert reading1.ph_is_estimated == False
    assert reading1.needs_ph_update == False

    # Verify reading2 is still pending
    db_session.refresh(reading2)
    assert reading2.needs_ph_update == True
    assert reading2.ph == 5.1

    # 4. Act: Update the second one
    payload2 = {"ph": 6.2}
    response2 = client.post(f"/iot/experiments/EXP-TEST-01/update-ph", json=payload2)
    
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["updated_reading_id"] == reading2.id
    assert data2["new_ph"] == 6.2

    db_session.refresh(reading2)
    assert reading2.ph == 6.2
    assert reading2.ph_is_estimated == False
    assert reading2.needs_ph_update == False

def test_update_ph_no_pending_records(client: TestClient, db_session: Session):
    """
    Test that the endpoint returns 404/message if no pending records exist.
    """
    experiment = models.Experiment(experiment_id="EXP-TEST-02")
    db_session.add(experiment)
    db_session.commit()

    # Create one reading that DOES NOT need update
    reading = models.DailyReading(
        experiment_id=experiment.id,
        ph=6.0,
        ph_is_estimated=False,
        needs_ph_update=False
    )
    db_session.add(reading)
    db_session.commit()

    payload = {"ph": 6.5}
    response = client.post(f"/iot/experiments/EXP-TEST-02/update-ph", json=payload)
    
    assert response.status_code == 404
    assert "No pending pH updates" in response.json()["detail"]

def test_update_ph_invalid_experiment(client: TestClient):
    """
    Test that it returns 404 if the experiment doesn't exist.
    """
    payload = {"ph": 6.5}
    response = client.post(f"/iot/experiments/NON-EXISTENT/update-ph", json=payload)
    assert response.status_code == 404
    assert "Experiment not found" in response.json()["detail"]

def test_new_reading_defaults_to_needs_update(client: TestClient, db_session: Session):
    """
    Test that new readings created via the API have needs_ph_update=True by default.
    """
    # 1. Test /iot/sensor_data/
    payload = {
        "temperature": 25.0,
        "ec": 1.5,
        "ph": 6.0,
        "ph_is_estimated": True,
        "experiment_id": "EXP-INGEST-01"
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    reading_id = response.json()["reading_id"]
    
    reading = db_session.query(models.DailyReading).get(reading_id)
    assert reading.needs_ph_update == True

    # 2. Test /iot/upload_data/ (Multipart)
    import io
    from PIL import Image
    
    # Create a dummy image
    img = Image.new('RGB', (100, 100), color=(73, 109, 137))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    files = {'image': ('test.jpg', img_byte_arr, 'image/jpeg')}
    data = {
        'ph': 6.1,
        'ec': 1.6,
        'temp': 26.0,
        'bucket_label': 'NPK'
    }
    
    response2 = client.post("/iot/upload_data/", data=data, files=files)
    assert response2.status_code == 200
    
    # Get the latest reading
    latest_reading = db_session.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert latest_reading.ph == 6.1
    assert latest_reading.needs_ph_update == True
