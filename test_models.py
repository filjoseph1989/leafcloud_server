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

def test_daily_reading_status_exists(db):
    # This test will fail if 'status' column is not added to models.py
    new_reading = models.DailyReading(
        ph=6.5,
        ec=1.5,
        water_temp=22.0,
        status="active" # This is the new field
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    assert new_reading.status == "active"
