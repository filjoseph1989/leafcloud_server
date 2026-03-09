import pytest
from fastapi.testclient import TestClient
from main import app, video_manager

@pytest.fixture
def client():
    # Use the client with the already-running VideoManager
    with TestClient(app) as c:
        yield c

def test_restart_flow(client, mocker):
    """
    Verifies the full restart flow: Mobile triggers -> flag set -> Pi polls -> Pi acknowledges -> flag reset.
    """
    # 1. Initial State: restart_requested should be False (or missing initially)
    # Note: We need to update the model/main first to even have this key.
    response = client.get("/control/current-status")
    assert response.status_code == 200
    data = response.json()
    # This will fail initially because the key doesn't exist in the current implementation.
    assert "restart_requested" in data
    assert data["restart_requested"] is False

    # 2. Mobile triggers restart
    # Mock video_manager.stop and start to ensure they are called
    mock_stop = mocker.patch.object(video_manager, 'stop')
    mock_start = mocker.patch.object(video_manager, 'start')

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
