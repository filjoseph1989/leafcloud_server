import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker, Session
from database import Base, get_db
import models
from datetime import datetime
import uuid

# Use in-memory database for performance tests to avoid locking issues
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# We must import app AFTER defining the engine if we want to be safe, 
# but here we use dependency overrides anyway.
from main import app

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    # Create dummy data
    exp = models.Experiment(experiment_id="EXP-TEST", bucket_label="NPK")
    db.add(exp)
    db.commit()
    db.refresh(exp)
    
    # Create the images directory if it doesn't exist
    if not os.path.exists("images"):
        os.makedirs("images")
        
    for i in range(10):
        filename = f"test_image_{i}.jpg"
        reading = models.DailyReading(
            experiment_id=exp.id,
            image_path=f"images/{filename}",
            ph=6.0,
            ec=1.2,
            water_temp=25.0
        )
        db.add(reading)
        # Create dummy file
        with open(f"images/{filename}", "w") as f:
            f.write("dummy")
            
    db.commit()
    db.close()
    
    yield
    
    # Cleanup images
    for i in range(10):
        if os.path.exists(f"images/test_image_{i}.jpg"):
            os.remove(f"images/test_image_{i}.jpg")
    
    engine.dispose()

def test_list_images_functionality():
    response = client.get("/admin/images/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    for item in data:
        assert item["bucket_label"] == "NPK"
        assert "image_url" in item
        assert not item["is_orphaned"]
