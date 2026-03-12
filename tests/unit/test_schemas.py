from pydantic import ValidationError
import pytest
from controllers.iot_controller import SensorData

def test_sensor_data_valid():
    data = {
        "temperature": 25.5,
        "ec": 1.2,
        "ph": 6.0,
        "status": "active",
        "timestamp": "2026-03-01T12:00:00"
    }
    sensor_data = SensorData(**data)
    assert sensor_data.temperature == 25.5
    assert sensor_data.ec == 1.2
    assert sensor_data.ph == 6.0
    assert sensor_data.status == "active"

def test_sensor_data_invalid():
    data = {
        "temperature": "not a number",
        "ec": 1.2,
        "ph": 6.0
    }
    with pytest.raises(ValidationError):
        SensorData(**data)
