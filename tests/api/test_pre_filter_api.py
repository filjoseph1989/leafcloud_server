import pytest
import os
import shutil
from unittest.mock import patch
from models import AutomatedActionLog

def test_pre_filter_images_endpoint(client, mocker):
    """Verify that the pre-filter endpoint calls process_image_batch and returns stats."""
    
    mock_stats = {
        "deleted_metadata": 2,
        "deleted_corrupted": 1,
        "moved_to_trash": 5,
        "kept": 10,
        "total_processed": 18
    }
    
    # Mock the utility function
    mock_process = mocker.patch("image_filtering.process_image_batch", return_value=mock_stats)
    
    payload = {
        "size_threshold": 2000,
        "green_threshold": 45.5
    }
    
    # We'll use the /api/v1/images/pre-filter endpoint as per spec
    response = client.post("/api/v1/images/pre-filter", json=payload)
    
    # Should fail if not implemented (404) or implemented differently
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "success"
    assert data["stats"] == mock_stats
    
    # Verify mock was called with correct parameters
    mock_process.assert_called_once()
    args, kwargs = mock_process.call_args
    assert args[2] == 2000 # size_threshold
    assert args[3] == 45.5 # green_threshold

def test_pre_filter_logging_integration(client, db_session, tmp_path, mocker):
    """Verify that the pre-filter endpoint actually saves logs to the database."""
    import image_filtering
    
    # 1. Setup mock images dir
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    
    # 2. Create a file that will be moved to trash
    filename = "bad_image.jpg"
    bad_file = image_dir / filename
    bad_file.write_text("a" * 2000)
    
    # 3. Patch process_image_batch to use our temp directories AND the db session
    from image_filtering import process_image_batch as original_process
    mocker.patch("main.image_filtering.process_image_batch", side_effect=lambda d, t, s, g, db=None: original_process(str(image_dir), str(tmp_path / "temp_trash"), s, g, db=db))

    payload = {
        "size_threshold": 1000,
        "green_threshold": 99.0 # Very high to ensure it's moved
    }
    
    response = client.post("/api/v1/images/pre-filter", json=payload)
    
    assert response.status_code == 200
    
    # Verify log entry in DB
    logs = db_session.query(AutomatedActionLog).filter(AutomatedActionLog.filename == filename).all()
    assert len(logs) == 1
    assert logs[0].action_type == "move_to_trash"
    assert logs[0].reason == "low_greenness"
