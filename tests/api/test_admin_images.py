import pytest
import os
import shutil
from datetime import datetime
import models

@pytest.fixture
def setup_test_env(db_session):
    # Setup Mock Images Dir
    test_image_dir = "images"
    if not os.path.exists(test_image_dir):
        os.makedirs(test_image_dir)
    
    # Create a real synced image
    synced_filename = "synced_test.jpg"
    synced_path = os.path.join(test_image_dir, synced_filename)
    with open(synced_path, "w") as f:
        f.write("mock data")
        
    # Create an orphaned image
    orphaned_filename = "orphaned_test.jpg"
    orphaned_path = os.path.join(test_image_dir, orphaned_filename)
    with open(orphaned_path, "w") as f:
        f.write("mock data")

    # Seed DB record for synced image
    experiment = models.Experiment(experiment_id="EXP-ADMIN-TEST", bucket_label="test", start_date=datetime.now().date())
    db_session.add(experiment)
    db_session.commit()
    db_session.refresh(experiment)
    
    reading = models.DailyReading(
        experiment_id=experiment.id,
        ph=6.0,
        ec=1.0,
        water_temp=20.0,
        image_path=f"images/{synced_filename}",
        timestamp=datetime.now()
    )
    db_session.add(reading)
    db_session.commit()
    
    yield
    
    # Cleanup
    if os.path.exists(synced_path):
        os.remove(synced_path)
    if os.path.exists(orphaned_path):
        os.remove(orphaned_path)

def test_list_images_endpoint(client, setup_test_env):
    """Verify that images are listed and correctly identified as synced or orphaned."""
    # Use a high limit to ensure our test files are found among other images in the dir
    response = client.get("/admin/images/?limit=1000")
    assert response.status_code == 200
    data = response.json()
    
    # Check synced image
    synced = next((item for item in data if item["filename"] == "synced_test.jpg"), None)
    assert synced is not None
    assert synced["is_orphaned"] is False
    assert synced["reading_id"] is not None
    
    # Check orphaned image
    orphaned = next((item for item in data if item["filename"] == "orphaned_test.jpg"), None)
    assert orphaned is not None
    assert orphaned["is_orphaned"] is True
    assert orphaned["reading_id"] is None
