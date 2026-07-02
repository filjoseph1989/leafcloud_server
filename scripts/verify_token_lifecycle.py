import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.database import Base, get_db
from app.models.user import User
from app.models.tank_config import TankConfig
from app.core.security import get_password_hash

# Setup temporary sqlite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_temp_lifecycle.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables in sqlite test db
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

# Seed database with dummy user and config
db = TestingSessionLocal()
hashed_user_pass = get_password_hash("user123")
standard_user = User(name="Test User", email="user_lifecycle@leafcloud.com", hashed_password=hashed_user_pass, is_admin=False)
db.add(standard_user)

config = TankConfig(
    tank_name="Test Tank",
    water_volume_liters=100.0,
    macro_brand_name="Brand A",
    macro_n_pct=5.0,
    macro_p_pct=1.0,
    macro_k_pct=3.0,
    macro_density=1.0,
    micro_brand_name="Brand B",
    micro_n_pct=0.5,
    micro_p_pct=0.1,
    micro_k_pct=0.3,
    micro_density=1.0,
    target_macro_dosage_mll=0.2,
    target_micro_dosage_mll=0.1,
    upload_interval_seconds=60,
    is_active=True
)
db.add(config)
db.commit()
db.close()

# Apply overrides
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

print("\n--- Starting Token Lifecycle Verification ---")

# Test 1: Login and verify access token and refresh token
print("Test 1: User Login (Should return access and refresh tokens)")
res = client.post("/api/v1/auth/login", json={"email": "user_lifecycle@leafcloud.com", "password": "user123"})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
payload = res.json()
assert "token" in payload, "Access token missing in response"
assert "refresh_token" in payload, "Refresh token missing in response"
access_token1 = payload["token"]
refresh_token1 = payload["refresh_token"]
print("Test 1 Passed!")

# Test 2: Access protected route with access token
print("Test 2: Access protected route /api/v1/tank-configs/ (Should be allowed)")
headers1 = {"Authorization": f"Bearer {access_token1}"}
res = client.get("/api/v1/tank-configs/", headers=headers1)
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
print("Test 2 Passed!")

# Test 3: Refresh access token using the refresh token (Rotation)
print("Test 3: Token Refresh/Rotation (Should return new token pair)")
res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token1})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
refresh_payload = res.json()
assert "token" in refresh_payload, "New access token missing"
assert "refresh_token" in refresh_payload, "New refresh token missing"
access_token2 = refresh_payload["token"]
refresh_token2 = refresh_payload["refresh_token"]
assert access_token1 != access_token2, "Access token should be regenerated"
assert refresh_token1 != refresh_token2, "Refresh token should be rotated"
print("Test 3 Passed!")

# Test 4: Reusing rotated refresh token (Should fail)
print("Test 4: Reusing rotated refresh token (Should fail with 401)")
res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token1})
assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"
print("Test 4 Passed!")

# Test 5: Verify new access token works
print("Test 5: Verify new access token works on protected route")
headers2 = {"Authorization": f"Bearer {access_token2}"}
res = client.get("/api/v1/tank-configs/", headers=headers2)
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
print("Test 5 Passed!")

# Test 6: Logout (Should blacklist active access token and revoke refresh token)
print("Test 6: User Logout (Should revoke active session)")
res = client.post("/api/v1/auth/logout", headers=headers2, json={"refresh_token": refresh_token2})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
print("Test 6 Passed!")

# Test 7: Verify blacklisted access token is rejected
print("Test 7: Using blacklisted access token (Should fail with 401)")
res = client.get("/api/v1/tank-configs/", headers=headers2)
assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"
assert "revoked" in res.json()["detail"].lower(), f"Expected revoked detail message, got: {res.text}"
print("Test 7 Passed!")

# Test 8: Verify revoked refresh token is rejected
print("Test 8: Using revoked refresh token (Should fail with 401)")
res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token2})
assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"
print("Test 8 Passed!")

# Clean up sqlite test db file
if os.path.exists("./test_temp_lifecycle.db"):
    os.remove("./test_temp_lifecycle.db")

print("\nAll token lifecycle tests completed successfully!")
