import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app
from datetime import date

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
    # Create a default experiment since sensor data needs one
    session = TestingSessionLocal(bind=connection)
    exp = models.Experiment(experiment_id="EXP-API-TEST", bucket_label="NPK", start_date=date.today())
    session.add(exp)
    session.commit()
    session.close()
    yield
    models.Base.metadata.drop_all(bind=connection)
    connection.close()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_sensor_data_ingestion_with_ph_estimated_true(client):
    """Test that ph_is_estimated=True is accepted and stored."""
    payload = {
        "temp": 25.0,
        "ec": 1.2,
        "ph": 6.0,
        "ph_is_estimated": True,
        "experiment_id": "EXP-API-TEST"
    }
    # Mock capture_frame to avoid failure
    from controllers import iot_controller
    iot_controller.capture_frame = lambda x: True

    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    
    # Verify in DB
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading.ph_is_estimated is True
    db.close()

def test_sensor_data_ingestion_with_ph_estimated_false(client):
    """Test that ph_is_estimated=False is accepted and stored (future proofing)."""
    payload = {
        "temp": 25.0,
        "ec": 1.2,
        "ph": 6.5,
        "ph_is_estimated": False,
        "experiment_id": "EXP-API-TEST"
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    
    # Verify in DB
    db = TestingSessionLocal(bind=connection)
    reading = db.query(models.DailyReading).order_by(models.DailyReading.id.desc()).first()
    assert reading.ph_is_estimated is False
    db.close()
