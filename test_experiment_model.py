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

def test_create_experiment(db):
    new_exp = models.Experiment(
        experiment_id="EXP-2026-001",
        bucket_label="BucketA-Balanced",
        start_date=date(2026, 3, 8)
    )
    db.add(new_exp)
    db.commit()
    db.refresh(new_exp)
    
    assert new_exp.id is not None
    assert new_exp.experiment_id == "EXP-2026-001"
    assert new_exp.bucket_label == "BucketA-Balanced"
    assert new_exp.start_date == date(2026, 3, 8)

def test_experiment_reading_relationship(db):
    new_exp = models.Experiment(
        experiment_id="EXP-2026-002",
        bucket_label="BucketB-LowN",
        start_date=date(2026, 3, 8)
    )
    db.add(new_exp)
    db.commit()
    
    new_reading = models.DailyReading(
        experiment_id=new_exp.id,
        ph=6.0,
        ec=1.2,
        water_temp=21.5
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_exp)
    
    assert len(new_exp.readings) == 1
    assert new_exp.readings[0].ph == 6.0
    assert new_exp.readings[0].experiment.experiment_id == "EXP-2026-002"
