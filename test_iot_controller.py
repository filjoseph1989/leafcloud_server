import pytest
import os
import shutil
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db, Base
import models
from datetime import date
from main import app
from controllers.iot_controller import init_iot_controller

# Use /tmp for test DB to avoid filesystem issues on external drives
SQLALCHEMY_DATABASE_URL = "sqlite:////tmp/test_temp.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Mock VideoManager
class MockVideoManager:
    def get_latest_frame(self):
        import numpy as np
        return np.zeros((480, 640, 3), dtype=np.uint8)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # Remove old test DB if exists
    if os.path.exists("/tmp/test_temp.db"):
        os.remove("/tmp/test_temp.db")
        
    # Use the local test engine to create tables
    models.Base.metadata.create_all(bind=engine)
    if not os.path.exists("images"):
        os.makedirs("images")
    
    # Create a default experiment so readings can be associated
    db = TestingSessionLocal()
    default_exp = models.Experiment(
        experiment_id="EXP-TEST-DEFAULT",
        bucket_label="default",
        start_date=date(2026, 3, 8)
    )
    db.add(default_exp)
    db.commit()
    db.close()

    # Initialize controller with mocks
    init_iot_controller(
        model=None,
        video_manager=MockVideoManager(),
        bucket_getter=lambda: None
    )
    
    yield
    # Cleanup
    if os.path.exists("/tmp/test_temp.db"):
        os.remove("/tmp/test_temp.db")

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_sensor_data_ingestion_status(client):
    """Should return 201 after migration."""
    payload = {
        "temperature": 25.0,
        "ec": 1.5,
        "ph": 6.5
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "success"

def test_upload_data_status(client):
    """Should return success after migration."""
    # Create a dummy image
    from PIL import Image
    import io
    img = Image.new('RGB', (100, 100), color = 'red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    files = {'image': ('test.jpg', img_byte_arr, 'image/jpeg')}
    data = {'ph': 6.0, 'ec': 1.0, 'temp': 20.0, 'bucket_label': 'test_bucket'}
    
    response = client.post("/iot/upload_data/", files=files, data=data)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
