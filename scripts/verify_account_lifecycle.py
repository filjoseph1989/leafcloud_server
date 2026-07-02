import sys
import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Add project root to sys.path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.database import Base, get_db
from app.models.user import User
from app.models.password_reset import PasswordResetToken
from app.core.security import get_password_hash
from app.core.config import settings

# Setup temporary sqlite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_temp_account.db"
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

# Seed database with dummy configs
db = TestingSessionLocal()
# Seeding empty user db for clean registry
db.commit()
db.close()

# Apply overrides
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

print("\n--- Starting Account Lifecycle Verification ---")

email = "user_account@leafcloud.com"
password = "password123"

# Test 1: Register user
print("Test 1: User Registration (Should register user as unverified)")
res = client.post("/api/v1/auth/register", json={
    "name": "Test User",
    "email": email,
    "password": password
})
assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
user_data = res.json()
assert user_data["is_verified"] is False, "User should not be verified on registration"
print("Test 1 Passed!")

# Test 2: Login unverified user (Should fail)
print("Test 2: Login unverified user (Should be rejected with 401)")
res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
assert res.status_code == 401, f"Expected 401, got {res.status_code}: {res.text}"
assert "not verified" in res.json()["detail"].lower(), "Verification detail missing"
print("Test 2 Passed!")

# Test 3: Account Verification
print("Test 3: Account Verification (GET /auth/verify)")
# Construct matching JWT token locally since we share SECRET_KEY
verify_token = jwt.encode(
    {"sub": email, "type": "verification", "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
    settings.SECRET_KEY,
    algorithm=settings.ALGORITHM
)
res = client.get(f"/api/v1/auth/verify?token={verify_token}")
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
assert res.json()["status"] == "success"
print("Test 3 Passed!")

# Test 4: Login verified user (Should succeed)
print("Test 4: Login verified user (Should succeed)")
res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
login_payload = res.json()
access_token = login_payload["token"]
refresh_token = login_payload["refresh_token"]
assert login_payload["user"]["is_verified"] is True
print("Test 4 Passed!")

# Test 5: Profile and password updates (PATCH /auth/me)
print("Test 5: Update User Profile & Password (PATCH /auth/me)")
headers = {"Authorization": f"Bearer {access_token}"}
res = client.patch("/api/v1/auth/me", headers=headers, json={
    "name": "Updated Name",
    "current_password": password,
    "new_password": "newpassword123"
})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
assert res.json()["name"] == "Updated Name"
print("Test 5 Passed!")

# Test 6: Verify old password fails and new password works
print("Test 6: Verify new credentials on login")
# Old password login (Should fail)
res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
assert res.status_code == 401
# New password login (Should succeed)
res = client.post("/api/v1/auth/login", json={"email": email, "password": "newpassword123"})
assert res.status_code == 200
login_payload2 = res.json()
access_token2 = login_payload2["token"]
refresh_token2 = login_payload2["refresh_token"]
print("Test 6 Passed!")

# Test 7: Forgot password flow
print("Test 7: Trigger forgot password")
res = client.post("/api/v1/auth/forgot-password", json={"email": email})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
# Query sqlite database to retrieve the reset token
db = TestingSessionLocal()
token_record = db.query(PasswordResetToken).filter(PasswordResetToken.email == email).first()
assert token_record is not None, "Reset token not saved in DB"
reset_token = token_record.token
db.close()
print("Test 7 Passed!")

# Test 8: Reset password using token
print("Test 8: Reset password with token")
res = client.post("/api/v1/auth/reset-password", json={
    "token": reset_token,
    "new_password": "forgotpassword123"
})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
print("Test 8 Passed!")

# Test 9: Verify reset password works on login
print("Test 9: Verify reset credentials on login")
res = client.post("/api/v1/auth/login", json={"email": email, "password": "forgotpassword123"})
assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
print("Test 9 Passed!")

# Clean up sqlite test db file
if os.path.exists("./test_temp_account.db"):
    os.remove("./test_temp_account.db")

print("\nAll account lifecycle tests completed successfully!")
