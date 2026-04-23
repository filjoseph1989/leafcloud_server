import pytest
import main

@pytest.fixture(autouse=True)
def reset_globals():
    main.active_bucket_id = None
    main.active_experiment_id = None
    yield
    main.active_bucket_id = None
    main.active_experiment_id = None

def test_get_current_status_initial(client):
    """
    Verifies that the initial status is null/None.
    """
    response = client.get("/control/current-status")
    assert response.status_code == 200
    assert response.json()["active_bucket_id"] is None
    assert response.json()["active_experiment_id"] is None

def test_post_active_experiment_valid(client):
    """
    Verifies that setting a valid experiment ID works.
    """
    payload = {"experiment_id": "EXP-2026-03"}
    response = client.post("/control/active-experiment", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["active_experiment_id"] == "EXP-2026-03"

    # Verify via GET
    status_response = client.get("/control/current-status")
    assert status_response.json()["active_experiment_id"] == "EXP-2026-03"

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

def test_calibration_flow(client):
    """
    Verifies the calibration request and acknowledgement flow.
    """
    # 1. Request EC calibration
    response = client.post("/control/request-calibration", json={"calibration_type": "ec"})
    assert response.status_code == 200
    assert response.json()["ec_calibration_requested"] is True
    
    # 2. Verify status
    status = client.get("/control/current-status").json()
    assert status["ec_calibration_requested"] is True
    assert status["ph_401_calibration_requested"] is False
    
    # 3. Request PH 4.01 calibration (should clear EC)
    response = client.post("/control/request-calibration", json={"calibration_type": "ph_4.01"})
    assert response.status_code == 200
    assert response.json()["ph_401_calibration_requested"] is True
    assert response.json()["ec_calibration_requested"] is False
    
    # 4. Acknowledge
    response = client.post("/control/acknowledge-calibration")
    assert response.status_code == 200
    
    # 5. Verify status cleared
    status = client.get("/control/current-status").json()
    assert status["ph_401_calibration_requested"] is False
    assert status["ec_calibration_requested"] is False

def test_calibration_invalid_type(client):
    """
    Verifies that invalid calibration types are rejected.
    """
    response = client.post("/control/request-calibration", json={"calibration_type": "invalid"})
    assert response.status_code == 422
