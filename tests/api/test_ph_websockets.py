import pytest
from fastapi.testclient import TestClient

def test_websocket_connection(client: TestClient):
    """
    Test that a client can connect to the pH stream WebSocket.
    """
    with client.websocket_connect("/iot/ph/stream") as websocket:
        # Just connecting and closing for now
        pass

def test_websocket_broadcast(client: TestClient):
    """
    Test that a message sent to the REST endpoint is broadcast to connected WS clients.
    """
    with client.websocket_connect("/iot/ph/stream") as websocket:
        payload = {
            "device_id": "WS_TEST_PI",
            "readings": [
                {
                    "timestamp": "2026-03-14T16:00:00",
                    "raw_adc": 20000,
                    "voltage": 3.0
                }
            ]
        }
        
        # Trigger broadcast via POST
        response = client.post("/iot/logs", json=payload)
        assert response.status_code == 200
        
        # Receive broadcast
        data = websocket.receive_json()
        assert data["device_id"] == "WS_TEST_PI"
        assert len(data["readings"]) == 1
        assert data["readings"][0]["raw_adc"] == 20000
