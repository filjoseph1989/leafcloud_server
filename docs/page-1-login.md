[Next](./page-2-database-setup.md)

# Authentication System: `POST /auth/login`

This document explains the authentication system implemented for LeafCloud Server V2.

## 1. Implementation Overview
We have implemented a robust and secure authentication system using **FastAPI**, **JWT (JSON Web Tokens)**, and **Bcrypt** for password hashing.

### Key Components:
*   **Security**: Uses `passlib` (bcrypt) for hashing and `python-jose` for JWT operations.
*   **Database**: Uses SQLAlchemy for the `User` model.
*   **Validation**: Uses Pydantic (including `email-validator`) for type safety and validation.
*   **Environment**: Sensitive data (secrets, admin credentials) are managed via the `.env` file.

---

## 2. How it Works (The Process)

When a user accesses the `/auth/login` endpoint:

1.  **Request Validation**: Pydantic checks if the JSON body has a valid `email` format and `password` string.
2.  **User Lookup**: The server searches the database (`users` table) for a user with the matching email.
3.  **Password Verification**: 
    *   If a user is found, the plain-text password from the request is compared to the `hashed_password` in the database using `bcrypt`.
    *   If they don't match or the user doesn't exist, a `401 Unauthorized` error is returned.
4.  **JWT Generation**: 
    *   If verification is successful, the server creates a JWT access token.
    *   The token contains the `sub` (subject/email), `user_id`, and `exp` (expiration time).
5.  **Response**: A JSON response is returned containing the status, the actual token, and basic user information.

---

## 3. Automatic Admin Seeding
For initial setup, there is a **startup event** in `app/main.py`.

*   When the server starts, it checks if an admin user already exists in the database.
*   If not, it automatically creates an admin account based on the `.env` settings:
    *   **Email**: `admin@leafcloud.com`
    *   **Name**: `Super Admin`
    *   **Password**: `admin123`

---

## 4. How to Use

### A. Starting the Server
Ensure you are using the correct environment:
```bash
~/.env_leafcloud/bin/uvicorn app.main:app --reload
```

### B. Testing Login (via cURL)
```bash
curl -X POST "http://localhost:8000/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "admin@leafcloud.com",
       "password": "admin123"
     }'
```

### C. Sample Response
```json
{
  "status": "success",
  "token": "eyJhbGciOiJIUzI1NiI...",
  "message": "Login successful",
  "user": {
    "id": 1,
    "name": "Super Admin",
    "email": "admin@leafcloud.com"
  }
}
```

---

## 5. Technical Details for Developers

*   **Endpoint**: `POST /auth/login`
*   **Files Involved**:
    *   `app/main.py`: Route handler and seeding logic.
    *   `app/auth.py`: JWT creation and password verification logic.
    *   `app/models.py`: Database schema for the `User`.
    *   `app/schemas.py`: Request (`LoginRequest`) and Response (`LoginResponse`) schemas.
    *   `app/database.py`: DB engine and session setup.
*   **Requirements**: See `requirements.txt` for the list of dependencies.

---

[Next](./page-2-database-setup.md)
