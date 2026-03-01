import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db
import models
import main
from main import app

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
    # Force creation of all tables on the test engine
    models.Base.metadata.create_all(bind=test_engine)
    yield
    models.Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest.fixture
def client(setup_db):
    with TestClient(app) as c:
        yield c

def test_post_sensor_data(client):
    payload = {
        "temperature": 25.5,
        "ec": 1.2,
        "ph": 6.0,
        "status": "active"
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["temperature"] == 25.5
