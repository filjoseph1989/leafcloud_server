import pytest
import os
import models
from datetime import datetime

@pytest.fixture
def setup_test_env(db_session):
    # Setup Mock Images Dir
    test_image_dir = "images"
    if not os.path.exists(test_image_dir):
        os.makedirs(test_image_dir)
    
    # Create a real synced image
    synced_filename = "synced_delete_test.jpg"
    synced_path = os.path.join(test_image_dir, synced_filename)
    with open(synced_path, "w") as f:
        f.write("mock data")
        
    # Create an orphaned image
    orphaned_filename = "orphaned_delete_test.jpg"
    orphaned_path = os.path.join(test_image_dir, orphaned_filename)
    with open(orphaned_path, "w") as f:
        f.write("mock data")

    # Seed DB record for synced image
    experiment = models.Experiment(experiment_id="EXP-DELETE-TEST", bucket_label="test", start_date=datetime.now().date())
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
    
    # Cleanup (only if tests didn't delete them)
    for f in [synced_filename, orphaned_filename, "prefix_test.jpg"]:
        p = os.path.join(test_image_dir, f)
        if os.path.exists(p):
            os.remove(p)

def test_delete_image_unauthorized(client):
    """Should return 401 if token is missing or invalid."""
    response = client.delete("/admin/images/synced_delete_test.jpg")
    assert response.status_code == 401

def test_delete_image_non_existent(client):
    """Should return 404 if file does not exist."""
    headers = {"Authorization": "demo-access-token-xyz-789"}
    response = client.delete("/admin/images/non_existent.jpg", headers=headers)
    assert response.status_code == 404

def test_delete_image_synced_success(client, db_session, setup_test_env):
    """Should delete file and DB record."""
    filename = "synced_delete_test.jpg"
    headers = {"Authorization": "demo-access-token-xyz-789"}
    
    # Verify before
    assert os.path.exists(os.path.join("images", filename))
    assert db_session.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{filename}")).first() is not None

    response = client.delete(f"/admin/images/{filename}", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify after
    assert not os.path.exists(os.path.join("images", filename))
    assert db_session.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{filename}")).first() is None

def test_delete_image_orphaned_success(client, setup_test_env):
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

def test_delete_image_with_prefix_success(client, setup_test_env):
    """Should delete file even if 'images/' prefix is passed in the path."""
    test_image_dir = "images"
    filename = "prefix_test.jpg"
    with open(os.path.join(test_image_dir, filename), "w") as f:
        f.write("mock data")
    
    headers = {"Authorization": "demo-access-token-xyz-789"}
    
    path_with_prefix = f"images/{filename}"
    
    response = client.delete(f"/admin/images/{path_with_prefix}", headers=headers)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert not os.path.exists(os.path.join("images", filename))
