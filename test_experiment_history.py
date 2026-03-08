import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app
from datetime import date, datetime, timedelta
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

def test_get_experiment_history_success(client):
    """Test retrieving history for an experiment with multiple readings."""
    # 1. Create an experiment
    exp_payload = {
        "experiment_id": "EXP-HIST-01",
        "bucket_label": "NPK",
        "start_date": str(date.today() - timedelta(days=2))
    }
    resp = client.post("/experiments/", json=exp_payload)
    exp_internal_id = resp.json()["id"]

    # 2. Add some readings manually to DB
    session = TestingSessionLocal(bind=connection)
    r1 = models.DailyReading(
        experiment_id=exp_internal_id,
        ph=6.0, ec=1.0, water_temp=20.0,
        bucket_label="NPK",
        timestamp=datetime.now() - timedelta(days=1)
    )
    r2 = models.DailyReading(
        experiment_id=exp_internal_id,
        ph=6.2, ec=1.1, water_temp=21.0,
        bucket_label="NPK",
        timestamp=datetime.now()
    )
    session.add_all([r1, r2])
    session.commit()
    session.close()

    # 3. Fetch history
    response = client.get(f"/experiments/{exp_internal_id}/history")
    assert response.status_code == 200
    data = response.json()
    assert data["experiment_id"] == "EXP-HIST-01"
    assert "NPK" in data["history"]
    assert len(data["history"]["NPK"]) == 2
    assert data["history"]["NPK"][0]["ph"] == 6.0

def test_get_experiment_history_not_found(client):
    """Test history for non-existent experiment."""
    response = client.get("/experiments/9999/history")
    assert response.status_code == 404
