import pytest
from unittest.mock import patch
from main import video_manager

def test_restart_flow(client):
    """
    Verifies the full restart flow: Mobile triggers -> flag set -> Pi polls -> Pi acknowledges -> flag reset.
    """
    # 1. Initial State: restart_requested should be False (or missing initially)
    response = client.get("/control/current-status")
    assert response.status_code == 200
    data = response.json()
    assert "restart_requested" in data
    assert data["restart_requested"] is False

    # 2. Mobile triggers restart
    # Mock video_manager.stop and start to ensure they are called
    with patch.object(video_manager, 'stop') as mock_stop, \
         patch.object(video_manager, 'start') as mock_start:

        response = client.post("/control/restart-iot")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["restart_requested"] is True
        
        # Verify VideoManager was restarted
        mock_stop.assert_called_once()
        mock_start.assert_called_once()

    # 3. Pi polls for status
    response = client.get("/control/current-status")
    assert response.status_code == 200
    assert response.json()["restart_requested"] is True

    # 4. Pi acknowledges restart
    response = client.post("/control/acknowledge-restart")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["restart_requested"] is False

    # 5. Verify final state
    response = client.get("/control/current-status")
    assert response.status_code == 200
    assert response.json()["restart_requested"] is False
