import pytest
import os
import shutil
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db, Base
import models
from main import app
from datetime import datetime

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:////tmp/test_images.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    # 1. Setup DB
    if os.path.exists("/tmp/test_images.db"):
        os.remove("/tmp/test_images.db")
    models.Base.metadata.create_all(bind=engine)
    
    # 2. Setup Mock Images Dir
    test_image_dir = "images"
    if not os.path.exists(test_image_dir):
        os.makedirs(test_image_dir)
    
    # Create a real synced image
    synced_filename = "synced_test.jpg"
    with open(os.path.join(test_image_dir, synced_filename), "w") as f:
        f.write("mock data")
        
    # Create an orphaned image
    orphaned_filename = "orphaned_test.jpg"
    with open(os.path.join(test_image_dir, orphaned_filename), "w") as f:
        f.write("mock data")

    # 3. Seed DB record for synced image
    db = TestingSessionLocal()
    experiment = models.Experiment(bucket_label="test", start_date=datetime.now().date())
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    
    reading = models.DailyReading(
        bucket_id=experiment.id,
        ph=6.0,
        ec=1.0,
        water_temp=20.0,
        bucket_label="test_bucket",
        image_path=f"images/{synced_filename}",
        timestamp=datetime.now()
    )
    db.add(reading)
    db.commit()
    db.close()
    
    yield
    
    # Cleanup
    if os.path.exists("/tmp/test_images.db"):
        os.remove("/tmp/test_images.db")
    if os.path.exists(os.path.join(test_image_dir, synced_filename)):
        os.remove(os.path.join(test_image_dir, synced_filename))
    if os.path.exists(os.path.join(test_image_dir, orphaned_filename)):
        os.remove(os.path.join(test_image_dir, orphaned_filename))

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_list_images_endpoint(client):
    """Verify that images are listed and correctly identified as synced or orphaned."""
    # Use a high limit to ensure our test files are found among other images in the dir
    response = client.get("/admin/images/?limit=1000")
    assert response.status_code == 200
    data = response.json()
    
    # Debug print if orphaned not found
    if not any(item["filename"] == "orphaned_test.jpg" for item in data):
        print(f"FILES IN DATA: {[item['filename'] for item in data]}")

    assert len(data) >= 2
    
    # Check synced image
    synced = next((item for item in data if item["filename"] == "synced_test.jpg"), None)
    assert synced is not None
    assert synced["is_orphaned"] is False
    assert synced["reading_id"] is not None
    assert synced["bucket_label"] == "test_bucket"
    
    # Check orphaned image
    orphaned = next((item for item in data if item["filename"] == "orphaned_test.jpg"), None)
    assert orphaned is not None
    assert orphaned["is_orphaned"] is True
    assert orphaned["reading_id"] is None
