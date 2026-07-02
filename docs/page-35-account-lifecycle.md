[Prev](./page-34-token-lifecycle.md) | [Next](./page-36-dashboard-ppm-analysis.md)

# Security: **Account Lifecycle Management**

This document explains the Account Lifecycle Management workflows implemented in the LeafCloud server. This resolves **[Authentication & Authorization Gaps](./page-32-auth-gaps.md)** (Gap #4: Account Lifecycle Management).

---

## 1. Overview
A production-ready application requires secure ways for users to activate accounts, keep their profiles up-to-date, and recover access when passwords are forgotten. We implement three lifecycle features:
1.  **Account Verification**: Registered users are initialized as unverified and blocked from logging in until they activate their account via a simulated email verification link.
2.  **Profile & Password Updates**: Logged-in users can update their profile (name, email) or modify their password. Changing the email or password automatically revokes all other active sessions (refresh tokens).
3.  **Password Recovery**: A secure forgot-password and reset-password workflow using time-limited, database-backed reset tokens.

---

## 2. Workflows & Implementation

### A. Account Verification
*   **Registration**: Upon `POST /auth/register`, the user's `is_verified` column defaults to `False`. The server generates a secure, signed JWT activation token valid for 24 hours containing the claim `{"sub": email, "type": "verification"}`.
*   **Email Simulation**: Since no SMTP server is configured, the server prints the verification link directly to the console/stdout:
    `[SIMULATED EMAIL] Click here to verify your account: http://localhost:8000/api/v1/auth/verify?token=...`
*   **Verification**: Calling `GET /auth/verify?token=...` decodes the token, checks the signature and expiry, and marks the user's `is_verified = True` in the database, allowing subsequent logins.

### B. Profile & Password Updates
*   **Endpoint**: `PATCH /api/v1/auth/me` (requires authentication).
*   **Name Change**: Modifies the `name` field directly.
*   **Email Change**: Checks if the new email is already registered. If not, updates the email and sets `is_verified = False` (generating a new simulated email link to verify the new email address). Additionally, all active refresh tokens for the user are revoked.
*   **Password Change**: Requires the payload to include `current_password` and `new_password`. Validates `current_password` against the stored hash. If valid, hashes the new password and revokes all active refresh tokens for the user to force re-authentication on all other devices.

### C. Password Recovery (Forgot/Reset)
*   **Forgot Password (`POST /auth/forgot-password`)**: Accepts `email`. Generates a secure random 32-byte hex token. Saves the token in the `password_reset_tokens` table with an expiration time set to +1 hour. Prints the reset link to stdout:
    `[SIMULATED EMAIL] Reset your password here: http://localhost:8000/api/v1/auth/reset-password?token=...`
*   **Reset Password (`POST /auth/reset-password`)**: Accepts `token` and `new_password`. Checks if the token exists, is not used (`is_used = False`), and is not expired. If valid, updates the user's password, marks the token as used (`is_used = True`), and revokes all active refresh tokens for the user to secure the account.

---

## 3. Database Schema

The password recovery system is backed by the `password_reset_tokens` table:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `email` | String(255) | The user email requesting the reset (Indexed). |
| `token` | String(255) | Unique random reset token (Unique index). |
| `expires_at` | DateTime | Timestamp when the token expires (+1 hour). |
| `created_at` | DateTime | Timestamp when the token was created. |
| `is_used` | Boolean | Whether the token has been consumed (default `False`). |

Additionally, the `users` table contains the column:
*   `is_verified`: Boolean, default `False` (server_default `'false'`), indicating email verification status.

---

## 4. Endpoints Reference

| Route Path | HTTP Method | Auth Required | Input Payload | Action Description |
| :--- | :---: | :---: | :--- | :--- |
| `/api/v1/auth/verify` | `GET` | None | Query: `token` | Verifies and activates user account |
| `/api/v1/auth/me` | `PATCH` | Bearer Token | `name`, `email`, `current_password`, `new_password` | Updates user details or changes password |
| `/api/v1/auth/forgot-password` | `POST` | None | `email` | Generates reset token and prints link |
| `/api/v1/auth/reset-password` | `POST` | None | `token`, `new_password` | Consumes reset token and updates password |

---

## 5. Verification

You can verify the entire account lifecycle (registration block, verification, updates, and forgot/reset password) by executing the test script:

```bash
/Users/fil/.env_leafcloud_3.11/bin/python3 scripts/verify_account_lifecycle.py
```
