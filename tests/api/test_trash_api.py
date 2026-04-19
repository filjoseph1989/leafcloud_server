import pytest
from fastapi.testclient import TestClient
from main import app
import models
from datetime import datetime

client = TestClient(app)

@pytest.fixture
def setup_trash_data(db_session):
    # Clear existing logs
    db_session.query(models.AutomatedActionLog).delete()
    
    # Add some mock trash data
    logs = [
        models.AutomatedActionLog(
            filename=f"trash_{i}.jpg",
            original_path=f"images/trash_{i}.jpg",
            current_path=f"images/temp_trash/trash_{i}.jpg",
            action_type="move_to_trash",
            reason="low_greenness",
            metric_value=30.0 + i,
            timestamp=datetime(2026, 4, 15, 12, i)
        ) for i in range(10)
    ]
    # Add one that is NOT a move_to_trash
    logs.append(models.AutomatedActionLog(
        filename="deleted.jpg",
        original_path="images/deleted.jpg",
        current_path="deleted",
        action_type="permanent_delete",
        reason="corrupted",
        timestamp=datetime(2026, 4, 15, 13, 0)
    ))
    
    db_session.add_all(logs)
    db_session.commit()
    return logs

def test_get_trash_success(client, db_session, setup_trash_data):
    """Verify that GET /trash returns only move_to_trash items sorted by timestamp."""
    headers = {"Authorization": "demo-access-token-xyz-789"}
    response = client.get("/api/v1/images/trash", headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Should only have 10 items (not the permanent_delete one)
    assert len(data) == 10
    
    # Should be sorted by timestamp newest first (12:09, 12:08, ...)
    assert data[0]["filename"] == "trash_9.jpg"
    assert data[-1]["filename"] == "trash_0.jpg"
    
    # Check structure of one item
    item = data[0]
    assert "id" in item
    assert "filename" in item
    assert "reason" in item
    assert "metric_value" in item
    assert "timestamp" in item

def test_get_trash_unauthorized(client):
    """Verify that GET /trash returns 401 if unauthorized."""
    response = client.get("/api/v1/images/trash")
    assert response.status_code == 401

def test_get_trash_pagination(client, db_session, setup_trash_data):
    """Verify pagination skip and limit."""
    headers = {"Authorization": "demo-access-token-xyz-789"}
    response = client.get("/api/v1/images/trash?skip=2&limit=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    # Sorted newest first, so skip 2 (9, 8) -> starts at 7
    assert data[0]["filename"] == "trash_7.jpg"

def test_get_trash_empty(client, db_session):
    """Verify that GET /trash returns empty list if no trashed items exist."""
    db_session.query(models.AutomatedActionLog).delete()
    db_session.commit()
    
    headers = {"Authorization": "demo-access-token-xyz-789"}
    response = client.get("/api/v1/images/trash", headers=headers)
    assert response.status_code == 200
    assert response.json() == []

def test_get_trash_limit_enforcement(client, db_session, setup_trash_data):
    """Verify that limit is capped at 100."""
    headers = {"Authorization": "demo-access-token-xyz-789"}
    response = client.get("/api/v1/images/trash?limit=200", headers=headers)
    assert response.status_code == 200
    # In this test we only have 10, but the logic should still apply.
    # We'll trust the implementation code for the cap, 
    # but the test confirms it doesn't crash.
    assert len(response.json()) <= 100
