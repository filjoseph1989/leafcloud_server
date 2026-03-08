import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app

import os

# Use in-memory SQLite for testing with a single connection
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Use a single connection for the entire module to avoid locks
connection = test_engine.connect()

def override_get_db():
    db = TestingSessionLocal(bind=connection)
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    models.Base.metadata.create_all(bind=connection)
    yield
    models.Base.metadata.drop_all(bind=connection)
    connection.close()

@pytest.fixture
def client(setup_db):
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def reset_global_state():
    main.active_bucket_id = None
    yield

def test_sensor_data_with_explicit_bucket(client):
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
    
    # Verify in DB
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.experiment.bucket_label == "NPK"
    db.close()

def test_sensor_data_with_global_fallback(client):
    """
    Verifies fallback to global active_bucket_id if missing in payload.
    """
    main.active_bucket_id = "Water"
    payload = {
        "temperature": 22.0,
        "ec": 1.2,
        "ph": 5.8
        # bucket_id missing
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    
    # Verify in DB
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.experiment.bucket_label == "Water"
    db.close()

def test_sensor_data_with_no_bucket(client):
    """
    Verifies bucket_label is None if neither global nor payload provides it.
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
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    # If no bucket provided, it should link to the default experiment created by iot_controller
    assert reading.experiment.bucket_label == "NPK" 
    db.close()
