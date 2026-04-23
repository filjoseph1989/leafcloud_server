import os
import pytest
import models
from datetime import datetime

@pytest.fixture
def seed_data(db_session):
    # Create tables (already handled by engine fixture in conftest.py)
    
    # Create dummy data
    exp = models.Experiment(experiment_id="EXP-TEST", bucket_label="NPK")
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)
    
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
        db_session.add(reading)
        # Create dummy file
        with open(f"images/{filename}", "w") as f:
            f.write("dummy")
            
    db_session.commit()
    
    yield
    
    # Cleanup images
    for i in range(10):
        if os.path.exists(f"images/test_image_{i}.jpg"):
            os.remove(f"images/test_image_{i}.jpg")

def test_list_images_functionality(client, seed_data):
    response = client.get("/admin/images/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    for item in data:
        assert item["bucket_label"] == "NPK"
        assert "image_url" in item
        assert not item["is_orphaned"]
