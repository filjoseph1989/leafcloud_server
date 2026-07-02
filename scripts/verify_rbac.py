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
from app.models.sensor_calibration import SensorCalibration
from app.core.security import get_password_hash

# Setup temporary sqlite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_temp.db"
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

# Seed database with some dummy tank configs and calibration sensor
db = TestingSessionLocal()
hashed_admin_pass = get_password_hash("admin123")
hashed_user_pass = get_password_hash("user123")

# Create test users
admin_user = User(name="Test Admin", email="admin_test@leafcloud.com", hashed_password=hashed_admin_pass, is_admin=True)
standard_user = User(name="Test User", email="user_test@leafcloud.com", hashed_password=hashed_user_pass, is_admin=False)
db.add_all([admin_user, standard_user])

# Create initial configurations and calibrations
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
calibration = SensorCalibration(
    sensor_name="temp_sensor",
    is_calibrating=False
)
db.add_all([config, calibration])
db.commit()
db.close()

# Apply overrides
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Helper function to get token
def get_token(email, password):
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["token"]

admin_token = get_token("admin_test@leafcloud.com", "admin123")
user_token = get_token("user_test@leafcloud.com", "user123")

print("\n--- Starting Verification ---")

headers_user = {"Authorization": f"Bearer {user_token}"}
headers_admin = {"Authorization": f"Bearer {admin_token}"}

# Test 1: GET /api/v1/tank-configs/
print("Test 1: Standard user GET /api/v1/tank-configs/")
res = client.get("/api/v1/tank-configs/", headers=headers_user)
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
configs = res.json()
assert len(configs) >= 1, "Should have at least 1 config"
assert configs[0]["tank_name"] == "Test Tank"
print("Test 1 Passed!")

# Test 2: Standard user POST /api/v1/tank-configs/ (Should fail)
print("Test 2: Standard user POST /api/v1/tank-configs/ (Should be forbidden)")
new_config_payload = {
    "tank_name": "New Tank",
    "water_volume_liters": 50.0,
    "macro_n_pct": 5.0,
    "macro_p_pct": 1.0,
    "macro_k_pct": 3.0,
    "micro_n_pct": 0.5,
    "micro_p_pct": 0.1,
    "micro_k_pct": 0.3,
    "target_macro_dosage_mll": 0.2,
    "target_micro_dosage_mll": 0.1
}
res = client.post("/api/v1/tank-configs/", headers=headers_user, json=new_config_payload)
assert res.status_code == 403, f"Expected 403, got {res.status_code}"
print("Test 2 Passed!")

# Test 3: Admin user POST /api/v1/tank-configs/ (Should succeed)
print("Test 3: Admin user POST /api/v1/tank-configs/")
res = client.post("/api/v1/tank-configs/", headers=headers_admin, json=new_config_payload)
assert res.status_code == 201, f"Expected 201, got {res.status_code}"
created_config = res.json()
config_id = created_config["id"]
assert created_config["tank_name"] == "New Tank"
print("Test 3 Passed!")

# Test 4: Standard user PATCH /api/v1/tank-configs/{id} (Should fail)
print("Test 4: Standard user PATCH /api/v1/tank-configs/{id} (Should be forbidden)")
res = client.patch(f"/api/v1/tank-configs/{config_id}", headers=headers_user, json={"tank_name": "Modified Tank"})
assert res.status_code == 403, f"Expected 403, got {res.status_code}"
print("Test 4 Passed!")

# Test 5: Admin user PATCH /api/v1/tank-configs/{id} (Should succeed)
print("Test 5: Admin user PATCH /api/v1/tank-configs/{id}")
res = client.patch(f"/api/v1/tank-configs/{config_id}", headers=headers_admin, json={"tank_name": "Modified Tank"})
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert res.json()["tank_name"] == "Modified Tank"
print("Test 5 Passed!")

# Test 6: Standard user DELETE /api/v1/tank-configs/{id} (Should fail)
print("Test 6: Standard user DELETE /api/v1/tank-configs/{id} (Should be forbidden)")
res = client.delete(f"/api/v1/tank-configs/{config_id}", headers=headers_user)
assert res.status_code == 403, f"Expected 403, got {res.status_code}"
print("Test 6 Passed!")

# Test 7: Admin user DELETE /api/v1/tank-configs/{id} (Should succeed)
print("Test 7: Admin user DELETE /api/v1/tank-configs/{id}")
res = client.delete(f"/api/v1/tank-configs/{config_id}", headers=headers_admin)
assert res.status_code == 204, f"Expected 204, got {res.status_code}"
print("Test 7 Passed!")

# Test 8: Standard user PATCH /api/v1/calibration/{id} (Should fail)
print("Test 8: Standard user PATCH /api/v1/calibration/{id} (Should be forbidden)")
res = client.patch("/api/v1/calibration/1", headers=headers_user, json={"is_calibrating": True})
assert res.status_code == 403, f"Expected 403, got {res.status_code}"
print("Test 8 Passed!")

# Test 9: Admin user PATCH /api/v1/calibration/{id} (Should succeed)
print("Test 9: Admin user PATCH /api/v1/calibration/{id}")
res = client.patch("/api/v1/calibration/1", headers=headers_admin, json={"is_calibrating": True})
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
assert res.json()["is_calibrating"] is True
print("Test 9 Passed!")

# Clean up sqlite test db file
if os.path.exists("./test_temp.db"):
    os.remove("./test_temp.db")

print("\nAll tests completed successfully!")
