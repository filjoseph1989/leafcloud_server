import pytest
from fastapi.testclient import TestClient

def test_post_ph_logs_success(client: TestClient):
    """
    Test that the POST api/ph/logs endpoint correctly receives and validates
    batched sensor data.
    """
    payload = {
        "device_id": "TEST_PI_01",
        "readings": [
            {
                "timestamp": "2026-03-14T12:00:00",
                "raw_adc": 15000,
                "voltage": 2.5
            },
            {
                "timestamp": "2026-03-14T12:00:01",
                "raw_adc": 15100,
                "voltage": 2.51
            }
        ]
    }
    
    response = client.post("/iot/logs", json=payload)
    assert response.status_code == 200

    # Verify log file content
    import os
    log_file = "logs/ph_sensor.log"
    assert os.path.exists(log_file)
    with open(log_file, "r") as f:
        content = f.read()
        assert "TEST_PI_01" in content
        assert "15000" in content
        assert "15100" in content
        assert "2.5000V" in content

def test_post_ph_logs_invalid_payload(client: TestClient):
    """
    Test that the endpoint returns a validation error for malformed payloads.
    """
    # Missing 'readings' field
    payload = {
        "device_id": "TEST_PI_01"
    }
    
    response = client.post("/iot/logs", json=payload)
    assert response.status_code == 422  # FastAPI validation error
