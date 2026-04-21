import pytest
import os
import models
from datetime import datetime

@pytest.fixture
def setup_soft_delete_env(db_session):
    # Setup Mock Images Dir
    test_image_dir = "images"
    trash_dir = os.path.join(test_image_dir, "temp_trash")
    if not os.path.exists(test_image_dir):
        os.makedirs(test_image_dir)
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir)
    
    # Create a real synced image
    filename = "soft_delete_test.jpg"
    image_path = os.path.join(test_image_dir, filename)
    with open(image_path, "w") as f:
        f.write("mock data")

    # Seed DB record for synced image
    experiment = models.Experiment(experiment_id="EXP-SOFT-DELETE-TEST", bucket_label="test", start_date=datetime.now().date())
    db_session.add(experiment)
    db_session.commit()
    db_session.refresh(experiment)
    
    reading = models.DailyReading(
        experiment_id=experiment.id,
        ph=6.0,
        ec=1.0,
        water_temp=20.0,
        image_path=f"images/{filename}",
        timestamp=datetime.now(),
        status="active"
    )
    db_session.add(reading)
    db_session.commit()
    db_session.refresh(reading)
    
    # Add a prediction
    prediction = models.NPKPrediction(
        daily_reading_id=reading.id,
        predicted_n=100.0,
        predicted_p=50.0,
        predicted_k=150.0
    )
    db_session.add(prediction)
    db_session.commit()
    
    yield {
        "filename": filename,
        "image_path": image_path,
        "reading_id": reading.id,
        "trash_dir": trash_dir
    }
    
    # Cleanup
    if os.path.exists(image_path):
        os.remove(image_path)
    if os.path.exists(trash_dir):
        for f in os.listdir(trash_dir):
            os.remove(os.path.join(trash_dir, f))

def test_soft_delete_success(client, db_session, setup_soft_delete_env):
    """
    Test that DELETE /api/v1/images/{filename} now:
    1. Moves the file to temp_trash with UUID prefix.
    2. Soft-deletes the DailyReading (status='deleted').
    3. Keeps the NPKPrediction.
    4. Logs the action in AutomatedActionLog.
    """
    filename = setup_soft_delete_env["filename"]
    reading_id = setup_soft_delete_env["reading_id"]
    trash_dir = setup_soft_delete_env["trash_dir"]
    headers = {"Authorization": "demo-access-token-xyz-789"}

    # Execute DELETE
    response = client.delete(f"/api/v1/images/{filename}", headers=headers)
    assert response.status_code == 200
    assert "moved to trash" in response.json()["message"]

    # 1. Verify file moved to trash
    trash_files = os.listdir(trash_dir)
    found = [f for f in trash_files if filename in f and len(f) > len(filename) and not f.startswith("._")]
    assert len(found) == 1
    assert not os.path.exists(setup_soft_delete_env["image_path"])

    # 2. Verify DailyReading is soft-deleted
    reading = db_session.query(models.DailyReading).get(reading_id)
    assert reading is not None
    assert reading.status == "deleted"

    # 3. Verify NPKPrediction is NOT deleted
    prediction = db_session.query(models.NPKPrediction).filter(models.NPKPrediction.daily_reading_id == reading_id).first()
    assert prediction is not None

    # 4. Verify AutomatedActionLog entry
    log = db_session.query(models.AutomatedActionLog).filter(
        models.AutomatedActionLog.filename == filename,
        models.AutomatedActionLog.reason == "api_requested_delete"
    ).first()
    assert log is not None
    assert log.action_type == "move_to_trash"
    assert found[0] in log.current_path
