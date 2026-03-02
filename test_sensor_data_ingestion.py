import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app

import os

# Use a persistent SQLite file for testing to avoid in-memory connection issues
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# OVERRIDE ALL THE THINGS
main.engine = test_engine
main.Base = models.Base 

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def setup_db():
    # Force registration of models by importing them
    import models
    models.Base.metadata.create_all(bind=test_engine)
    yield
    models.Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test.db"):
        os.remove("./test.db")

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
    db = TestingSessionLocal()
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.bucket_label == "NPK"
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
    db = TestingSessionLocal()
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.bucket_label == "Water"
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
    db = TestingSessionLocal()
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading is not None
    assert reading.bucket_label is None
    db.close()
