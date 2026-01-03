import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load the database URL from an environment variable for security and flexibility.
# The default value is for a local setup with user 'fil' and no password.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get a DB session in API endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()