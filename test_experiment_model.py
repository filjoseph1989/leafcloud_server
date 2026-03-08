import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models
from datetime import date

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

def test_experiment_creation(db):
    """Test creating a new experiment with its ID and relationships."""
    new_exp = models.Experiment(
        experiment_id="EXP-001",
        bucket_label="NPK-Bucket-1",
        start_date=date.today()
    )
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    
    assert new_exp.id is not None
    assert new_exp.experiment_id == "EXP-001"
    assert new_exp.bucket_label == "NPK-Bucket-1"

def test_daily_reading_association(db):
    """Test linking a DailyReading to an Experiment."""
    new_exp = models.Experiment(
        experiment_id="EXP-002",
        start_date=date.today()
    )
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    
    new_reading = models.DailyReading(
        experiment_id=new_exp.id,
        ph=6.0,
        ec=1.2,
        water_temp=21.0
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    
    assert new_reading.experiment_id == new_exp.id
    assert len(new_exp.readings) == 1
    assert new_exp.readings[0].id == new_reading.id
