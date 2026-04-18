import pytest
import os
import shutil
from models import AutomatedActionLog

def test_restore_images_success(client, db_session, tmp_path):
    """Test successful restoration of images from trash."""
    # 1. Setup mock files
    trash_dir = tmp_path / "temp_trash"
    trash_dir.mkdir()
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    
    filename = "to_restore.jpg"
    trash_file = trash_dir / filename
    trash_file.write_text("dummy image data")
    
    original_path = str(original_dir / filename)
    
    # 2. Create log entry in DB
    log_entry = AutomatedActionLog(
        filename=filename,
        original_path=original_path,
        current_path=str(trash_file),
        action_type="move_to_trash",
        reason="low_greenness"
    )
    db_session.add(log_entry)
    db_session.commit()
    db_session.refresh(log_entry)
    
    log_id = log_entry.id
    
    # 3. Call restore API
    headers = {"Authorization": "demo-access-token-xyz-789"}
    payload = {"log_ids": [log_id]}
    
    response = client.post("/api/v1/images/restore", json=payload, headers=headers)
    
    # 4. Verify results
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # File moved back?
    assert os.path.exists(original_path)
    assert not os.path.exists(str(trash_file))
    
    # Log deleted?
    assert db_session.query(AutomatedActionLog).get(log_id) is None

def test_restore_images_unauthorized(client):
    """Test restoration fails without correct auth token."""
    response = client.post("/api/v1/images/restore", json={"log_ids": [1]})
    assert response.status_code == 401

def test_restore_images_missing_file(client, db_session, tmp_path):
    """Test restoration fails if file is missing from trash."""
    # 1. Create log entry for NON-EXISTENT file
    log_entry = AutomatedActionLog(
        filename="missing.jpg",
        original_path=str(tmp_path / "original.jpg"),
        current_path=str(tmp_path / "temp_trash" / "missing.jpg"),
        action_type="move_to_trash",
        reason="low_greenness"
    )
    db_session.add(log_entry)
    db_session.commit()
    
    # 2. Call restore API
    headers = {"Authorization": "demo-access-token-xyz-789"}
    payload = {"log_ids": [log_entry.id]}
    
    response = client.post("/api/v1/images/restore", json=payload, headers=headers)
    
    # 3. Verify failure (400 as per spec)
    assert response.status_code == 400
    assert "not found in trash" in response.json()["detail"]
    
    # Cleanup log if it stayed (though spec doesn't strictly say delete on failure)
    db_session.delete(log_entry)
    db_session.commit()
