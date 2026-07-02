[Prev](./page-33-rbac-implementation.md) | [Next](./page-35-account-lifecycle.md)

# Security: **Token Lifecycle Management (Access + Refresh Tokens)**

This document explains the dual-token (Access + Refresh) authentication system and token blacklisting mechanism implemented in the LeafCloud server. This resolves **[Authentication & Authorization Gaps](./page-32-auth-gaps.md)** (Gap #3: Basic Token Lifecycle Management).

---

## 1. Overview
Stateless JWT access tokens are convenient but cannot be invalidated on demand once issued. To bridge this security gap, we implement a dual-token setup with database-backed token management:
1.  **Access Token (Short-Lived JWT)**: Valid for 30 minutes, carries user context and a unique `jti` (JWT ID) claim.
2.  **Refresh Token (Long-Lived Database Token)**: Valid for 7 days, stored in the database. Used to request a new access token without re-entering credentials.
3.  **Refresh Token Rotation (RTR)**: Every time a refresh token is used, it is immediately revoked, and a new refresh token (and access token) pair is issued. This prevents replay attacks if a refresh token is intercepted.
4.  **Instant Logout (Access Token Blacklisting)**: On logout, the user's active access token's `jti` is added to a database blacklist table. Subsequent API requests using this token will be instantly rejected as unauthorized, even if the token has not reached its expiration timestamp.

---

## 2. Token Lifecycle Workflows

### Authentication Flow (Login)
```
[Client] ─── Login Credentials (email/password) ───> [Server]
[Client] <─── JSON Response {access_token, refresh_token} ─ [Server] (Generates & saves RefreshToken in DB)
```

### Accessing Protected API
```
[Client] ─── Request with Authorization Bearer JWT ───> [Server]
                                                         ├── Decode JWT and check "jti" claim
                                                         ├── Query "token_blacklist" for "jti"
                                                         └── If NOT blacklisted -> Grant Access (200 OK)
```

### Token Refresh / Rotation Flow
```
[Client] ─── POST /auth/refresh {refresh_token} ───> [Server]
                                                       ├── Check DB: exists, active, and not expired
                                                       ├── Revoke current RefreshToken in DB
                                                       ├── Generate new access_token & new refresh_token
                                                       └── Save new RefreshToken in DB
[Client] <─── New {access_token, refresh_token} ─────── [Server]
```

### Logout Flow
```
[Client] ─── POST /auth/logout {refresh_token} ───> [Server]
             (Header: Authorization Bearer JWT)        ├── Extract "jti" & "exp" from JWT
                                                       ├── Save "jti" to "token_blacklist" table
                                                       ├── Mark "refresh_token" as is_revoked = True
                                                       └── Commit to DB
[Client] <─── Logout Successful (200 OK) ─────────────── [Server]
```

---

## 3. Database Schema

Two new tables were added to support token lifecycle management:

### Table: `refresh_tokens`
Stores active session keys mapping users to refresh capabilities.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `token` | String(255) | Cryptographically secure random hex string (Unique index). |
| `user_id` | Integer | Foreign key referencing `users.id` (`ON DELETE CASCADE`). |
| `expires_at` | DateTime | Timestamp when the refresh token expires. |
| `created_at` | DateTime | Timestamp when the token was issued. |
| `is_revoked` | Boolean | Whether the token has been explicitly revoked or rotated (default `False`). |

### Table: `token_blacklist`
Stores revoked JWT identifiers (`jti`) until their original natural expiration time.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `jti` | String(255) | Unique JWT ID claim (Unique index). |
| `expires_at` | DateTime | The original expiration time of the revoked access token. |
| `blacklisted_at` | DateTime | Timestamp when the token was blacklisted. |

---

## 4. API Endpoints

### Login Response Payload
`POST /api/v1/auth/login`
Returns both access and refresh tokens.
```json
{
  "status": "success",
  "token": "access_token_jwt_string_here",
  "refresh_token": "63ad839174fe90...",
  "message": "Login successful",
  "user": {
    "id": 1,
    "name": "Super Admin",
    "email": "admin@leafcloud.com",
    "is_admin": true
  }
}
```

### Refresh Token Endpoint
`POST /api/v1/auth/refresh`
Request payload:
```json
{
  "refresh_token": "63ad839174fe90..."
}
```
Response payload (returns a brand new rotated pair):
```json
{
  "status": "success",
  "token": "new_access_token_jwt_string",
  "refresh_token": "new_rotated_refresh_token_hex",
  "message": "Token refreshed successfully"
}
```

### Logout Endpoint
`POST /api/v1/auth/logout`
Requires `Authorization: Bearer <access_token>` header.
Request payload:
```json
{
  "refresh_token": "active_refresh_token_hex"
}
```
Response payload:
```json
{
  "status": "success",
  "message": "Successfully logged out"
}
```

---

## 5. Verification

You can verify the entire lifecycle (login tokens issue, refresh rotation, replay protection, logout, and access token blacklist) by executing the test script:

```bash
/Users/fil/.env_leafcloud_3.11/bin/python3 scripts/verify_token_lifecycle.py
```
