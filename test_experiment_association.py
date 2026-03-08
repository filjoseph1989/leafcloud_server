import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app
from datetime import date, datetime
import os

# Use in-memory SQLite for testing with a single connection
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
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
def client():
    with TestClient(app) as c:
        yield c

def test_sensor_data_association_with_explicit_experiment_id(client):
    """Test associating sensor data with an explicit experiment_id (EXP-XXX)."""
    # 1. Create an experiment
    exp_payload = {
        "experiment_id": "EXP-501",
        "bucket_label": "NPK",
        "start_date": str(date.today())
    }
    client.post("/experiments/", json=exp_payload)

    # 2. Post sensor data with this experiment_id
    sensor_payload = {
        "temp": "24.5",
        "ec": "1.5",
        "ph": "6.2",
        "bucket_id": "NPK",
        "experiment_id": "EXP-501"
    }
    # Mock capture_frame to avoid failure
    from controllers import iot_controller
    iot_controller.capture_frame = lambda x: True

    response = client.post("/iot/sensor_data/", json=sensor_payload)
    if response.status_code != 201:
        print(response.json())
    assert response.status_code == 201
    
    # 3. Verify in DB
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    experiment = db.query(models.Experiment).filter(models.Experiment.experiment_id == "EXP-501").first()
    assert reading.experiment_id == experiment.id
    db.close()

def test_sensor_data_association_with_water_temp_alias(client):
    """Test associating sensor data when using 'water_temp' instead of 'temp'."""
    # 1. Create an experiment
    exp_payload = {
        "experiment_id": "EXP-503",
        "bucket_label": "Mixed",
        "start_date": str(date.today())
    }
    client.post("/experiments/", json=exp_payload)

    # 2. Post sensor data with 'water_temp'
    sensor_payload = {
        "water_temp": 22.5,
        "ec": 1.1,
        "ph": 6.1,
        "experiment_id": "EXP-503"
    }
    response = client.post("/iot/sensor_data/", json=sensor_payload)
    assert response.status_code == 201
    
    # 3. Verify in DB
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading.water_temp == 22.5
    db.close()
