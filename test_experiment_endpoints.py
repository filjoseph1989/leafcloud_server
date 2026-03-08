import pytest
import os
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

def test_create_experiment_success(client):
    """Test successful creation of an experiment."""
    payload = {
        "experiment_id": "EXP-101",
        "bucket_label": "NPK-Batch-A",
        "start_date": str(date.today())
    }
    response = client.post("/experiments/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["experiment_id"] == "EXP-101"
    assert "id" in data

def test_create_experiment_duplicate_id(client):
    """Test creating an experiment with a duplicate experiment_id."""
    payload = {
        "experiment_id": "EXP-101",
        "bucket_label": "NPK-Batch-B",
        "start_date": str(date.today())
    }
    # First one was created in the previous test
    response = client.post("/experiments/", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

def test_get_experiment_details(client):
    """Test retrieving details of an existing experiment."""
    # We know EXP-101 exists from previous test
    # First, let's find its internal ID
    session = TestingSessionLocal(bind=connection)
    exp = session.query(models.Experiment).filter(models.Experiment.experiment_id == "EXP-101").first()
    exp_internal_id = exp.id
    session.close()

    response = client.get(f"/experiments/{exp_internal_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["experiment_id"] == "EXP-101"
    assert data["bucket_label"] == "NPK-Batch-A"

def test_get_experiment_not_found(client):
    """Test retrieving a non-existent experiment."""
    response = client.get("/experiments/9999")
    assert response.status_code == 404
