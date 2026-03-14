import pytest
import models

def test_daily_reading_status_exists(db_session):
    # This test uses the db_session fixture from conftest.py
    new_reading = models.DailyReading(
        ph=6.5,
        ec=1.5,
        water_temp=22.0,
        status="active"
    )
    db_session.add(new_reading)
    db_session.commit()
    db_session.refresh(new_reading)
    assert new_reading.status == "active"
