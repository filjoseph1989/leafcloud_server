import pytest

def test_post_sensor_data(client):
    payload = {
        "temperature": 25.5,
        "ec": 1.2,
        "ph": 6.0,
        "status": "active"
    }
    response = client.post("/iot/sensor_data/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "reading_id" in data
    assert "experiment_id" in data
