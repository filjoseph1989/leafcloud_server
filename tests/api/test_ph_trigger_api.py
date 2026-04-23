import pytest
from fastapi.testclient import TestClient

def test_ph_update_trigger_flow(client: TestClient):
    """
    Test the full cycle of requesting and acknowledging a pH update.
    """
    # 1. Initial state check
    response = client.get("/control/current-status")
    assert response.status_code == 200
    assert response.json()["ph_update_requested"] is False

    # 2. Request pH update (Mobile App)
    response = client.post("/control/request-ph-update")
    assert response.status_code == 200
    assert response.json()["ph_update_requested"] is True

    # 3. Verify flag is set in status (Pi Polling)
    response = client.get("/control/current-status")
    assert response.json()["ph_update_requested"] is True

    # 4. Acknowledge pH update (IoT Device)
    response = client.post("/control/acknowledge-ph-update")
    assert response.status_code == 200
    assert response.json()["ph_update_requested"] is False

    # 5. Verify flag is cleared
    response = client.get("/control/current-status")
    assert response.json()["ph_update_requested"] is False
