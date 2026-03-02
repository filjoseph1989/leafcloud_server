import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_get_current_status_initial(client):
    """
    Verifies that the initial status is null/None.
    """
    response = client.get("/control/current-status")
    assert response.status_code == 200
    assert response.json()["active_bucket_id"] is None

def test_post_active_bucket_valid(client):
    """
    Verifies that setting a valid bucket works.
    """
    payload = {"bucket_id": "NPK"}
    response = client.post("/control/active-bucket", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["active_bucket_id"] == "NPK"

    # Verify via GET
    status_response = client.get("/control/current-status")
    assert status_response.json()["active_bucket_id"] == "NPK"

def test_post_active_bucket_stop(client):
    """
    Verifies that 'STOP' resets the status to None.
    """
    # Set to something first
    client.post("/control/active-bucket", json={"bucket_id": "Mix"})
    
    # Send STOP
    response = client.post("/control/active-bucket", json={"bucket_id": "STOP"})
    assert response.status_code == 200
    assert response.json()["active_bucket_id"] is None

    # Verify via GET
    status_response = client.get("/control/current-status")
    assert status_response.json()["active_bucket_id"] is None

def test_post_active_bucket_invalid(client):
    """
    Verifies that invalid bucket names are rejected (422).
    """
    payload = {"bucket_id": "InvalidBucket"}
    response = client.post("/control/active-bucket", json=payload)
    assert response.status_code == 422
