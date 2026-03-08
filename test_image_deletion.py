import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import get_db, Base
import models
from main import app
from datetime import datetime

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:////tmp/test_image_deletion.db"
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
    if os.path.exists("/tmp/test_image_deletion.db"):
        os.remove("/tmp/test_image_deletion.db")
    models.Base.metadata.create_all(bind=engine)
    
    # 2. Setup Mock Images Dir
    test_image_dir = "images"
    if not os.path.exists(test_image_dir):
        os.makedirs(test_image_dir)
    
    # Create a real synced image
    synced_filename = "synced_delete_test.jpg"
    with open(os.path.join(test_image_dir, synced_filename), "w") as f:
        f.write("mock data")
        
    # Create an orphaned image
    orphaned_filename = "orphaned_delete_test.jpg"
    with open(os.path.join(test_image_dir, orphaned_filename), "w") as f:
        f.write("mock data")

    # 3. Seed DB record for synced image
    db = TestingSessionLocal()
    experiment = models.Experiment(bucket_label="test", start_date=datetime.now().date())
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    
    reading = models.DailyReading(
        experiment_id=experiment.id,
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
    
    # Cleanup (only if tests didn't delete them)
    if os.path.exists("/tmp/test_image_deletion.db"):
        os.remove("/tmp/test_image_deletion.db")
    for f in ["synced_delete_test.jpg", "orphaned_delete_test.jpg", "prefix_test.jpg"]:
        p = os.path.join(test_image_dir, f)
        if os.path.exists(p):
            os.remove(p)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_delete_image_unauthorized(client):
    """Should return 401 if token is missing or invalid."""
    response = client.delete("/admin/images/synced_delete_test.jpg")
    assert response.status_code == 401

def test_delete_image_non_existent(client):
    """Should return 404 if file does not exist."""
    headers = {"Authorization": "demo-access-token-xyz-789"}
    response = client.delete("/admin/images/non_existent.jpg", headers=headers)
    assert response.status_code == 404

def test_delete_image_synced_success(client):
    """Should delete file and DB record."""
    filename = "synced_delete_test.jpg"
    headers = {"Authorization": "demo-access-token-xyz-789"}
    
    # Verify before
    assert os.path.exists(os.path.join("images", filename))
    db = TestingSessionLocal()
    assert db.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{filename}")).first() is not None
    db.close()

    response = client.delete(f"/admin/images/{filename}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify after
    assert not os.path.exists(os.path.join("images", filename))
    db = TestingSessionLocal()
    assert db.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{filename}")).first() is None
    db.close()

def test_delete_image_orphaned_success(client):
    """Should delete file from disk even if no DB record."""
    filename = "orphaned_delete_test.jpg"
    headers = {"Authorization": "demo-access-token-xyz-789"}
    
    # Verify before
    assert os.path.exists(os.path.join("images", filename))

    response = client.delete(f"/admin/images/{filename}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify after
    assert not os.path.exists(os.path.join("images", filename))

def test_delete_image_with_prefix_success(client):
    """Should delete file even if 'images/' prefix is passed in the path."""
    test_image_dir = "images"
    filename = "prefix_test.jpg"
    with open(os.path.join(test_image_dir, filename), "w") as f:
        f.write("mock data")
    
    headers = {"Authorization": "demo-access-token-xyz-789"}
    
    # Path with prefix. We need to handle this because FastAPI path parameters
    # might split on '/', so we use a path parameter like {filename:path} in implementation
    # if we want to support full paths, but for now we just test the stripping logic.
    path_with_prefix = f"images/{filename}"
    
    # In FastAPI, /admin/images/images/test.jpg would be 404 unless route is {filename:path}
    # Let's see if our implementation works with standard encoding or needs route adjustment.
    response = client.delete(f"/admin/images/{path_with_prefix}", headers=headers)
    
    # If this is 404, it's because FastAPI doesn't match the route with slashes in param
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert not os.path.exists(os.path.join("images", filename))
