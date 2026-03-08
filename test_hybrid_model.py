import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_daily_reading_ph_is_estimated_exists(db):
    """Test that ph_is_estimated field exists and can be set."""
    new_reading = models.DailyReading(
        ph=6.0,
        ec=1.5,
        water_temp=22.0,
        ph_is_estimated=True
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    assert new_reading.ph_is_estimated is True

def test_daily_reading_ph_is_estimated_default(db):
    """Test that ph_is_estimated field defaults to True."""
    new_reading = models.DailyReading(
        ph=6.0,
        ec=1.5,
        water_temp=22.0
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    assert new_reading.ph_is_estimated is True
