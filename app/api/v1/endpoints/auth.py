from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core import security
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, TokenRefreshRequest, TokenRefreshResponse, LogoutRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user or not security.verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not verified. Please verify your email first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = security.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    refresh_token = security.create_refresh_token(db=db, user_id=user.id)

    return {
        "status": "success",
        "token": access_token,
        "refresh_token": refresh_token,
        "message": "Login successful",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_verified": user.is_verified
        }
    }

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user and generates a simulated activation link."""
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already registered"
        )
    
    hashed_password = security.get_password_hash(request.password)
    
    new_user = User(
        name=request.name,
        email=request.email,
        hashed_password=hashed_password,
        is_verified=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate verification token (signed JWT valid for 24h)
    verify_token = security.jwt.encode(
        {"sub": new_user.email, "type": "verification", "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
        security.settings.SECRET_KEY,
        algorithm=security.settings.ALGORITHM
    )
    
    # Log simulated verification email link
    print(f"\n[SIMULATED EMAIL] Click here to verify your account: http://localhost:8000/api/v1/auth/verify?token={verify_token}\n")
    
    return new_user

@router.get("/verify")
def verify_account(token: str, db: Session = Depends(get_db)):
    """Verifies a newly registered user account via a token link."""
    try:
        payload = security.jwt.decode(token, security.settings.SECRET_KEY, algorithms=[security.settings.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "verification":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token")
    except security.JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired or invalid verification token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        return {"status": "success", "message": "Account already verified"}

    user.is_verified = True
    db.commit()
    return {"status": "success", "message": "Account successfully verified!"}

@router.patch("/me", response_model=UserResponse)
def update_profile(
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(security.get_current_user)
):
    """Updates profile properties or password for the current authenticated user."""
    needs_refresh_revoke = False

    if update_data.name is not None:
        current_user.name = update_data.name

    if update_data.email is not None and update_data.email != current_user.email:
        # Check if email is already in use
        existing = db.query(User).filter(User.email == update_data.email).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address already registered")
        
        current_user.email = update_data.email
        current_user.is_verified = False  # Require re-verification
        needs_refresh_revoke = True

        # Generate new verification token
        verify_token = security.jwt.encode(
            {"sub": current_user.email, "type": "verification", "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
            security.settings.SECRET_KEY,
            algorithm=security.settings.ALGORITHM
        )
        print(f"\n[SIMULATED EMAIL] Email changed. Click here to re-verify: http://localhost:8000/api/v1/auth/verify?token={verify_token}\n")

    if update_data.new_password is not None:
        # Password change requires current password validation
        if not update_data.current_password or not security.verify_password(update_data.current_password, current_user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password")
        
        current_user.hashed_password = security.get_password_hash(update_data.new_password)
        needs_refresh_revoke = True

    if needs_refresh_revoke:
        # Revoke all active refresh sessions to force re-authentication
        db.query(security.RefreshToken).filter(
            security.RefreshToken.user_id == current_user.id
        ).update({security.RefreshToken.is_revoked: True}, synchronize_session=False)

    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Forgot password endpoint. Generates a reset token and prints simulated link."""
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        # Generate secure random token
        import secrets
        reset_token = secrets.token_hex(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        from app.models.password_reset import PasswordResetToken
        db_reset = PasswordResetToken(
            email=user.email,
            token=reset_token,
            expires_at=expires_at
        )
        db.add(db_reset)
        db.commit()

        # Log simulated password recovery link
        print(f"\n[SIMULATED EMAIL] Reset your password here: http://localhost:8000/api/v1/auth/reset-password?token={reset_token}\n")

    # Always return success to prevent email enumeration
    return {"status": "success", "message": "If this email is registered, a password reset link has been sent."}

RESET_FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Password | LeafCloud</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
        }
        body {
            background: radial-gradient(circle at 10% 20%, rgb(18, 20, 36) 0%, rgb(9, 10, 15) 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }
        .blob {
            position: absolute;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.15;
            z-index: 1;
            animation: float 10s ease-in-out infinite alternate;
        }
        .blob-1 {
            width: 300px;
            height: 300px;
            background: #3b82f6;
            top: 20%;
            left: 10%;
        }
        .blob-2 {
            width: 250px;
            height: 250px;
            background: #10b981;
            bottom: 20%;
            right: 15%;
            animation-delay: -5s;
        }
        @keyframes float {
            0% { transform: translateY(0) scale(1); }
            100% { transform: translateY(30px) scale(1.1); }
        }
        .container {
            z-index: 10;
            width: 100%;
            max-width: 420px;
            padding: 20px;
        }
        .card {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            color: #fff;
            text-align: center;
        }
        .logo {
            font-size: 28px;
            font-weight: 800;
            background: linear-gradient(135deg, #10b981 0%, #3b82f6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }
        .title {
            font-size: 22px;
            font-weight: 600;
            color: #f3f4f6;
            margin-bottom: 24px;
        }
        .form-group {
            text-align: left;
            margin-bottom: 20px;
        }
        label {
            display: block;
            font-size: 14px;
            font-weight: 400;
            color: #9ca3af;
            margin-bottom: 8px;
            padding-left: 4px;
        }
        input {
            width: 100%;
            padding: 14px 18px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            color: #fff;
            font-size: 16px;
            outline: none;
            transition: all 0.3s ease;
        }
        input:focus {
            border-color: #10b981;
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.2);
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            border: none;
            border-radius: 12px;
            color: #fff;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 10px;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
        }
        button:active {
            transform: translateY(0);
        }
        .message {
            margin-top: 15px;
            font-size: 14px;
            border-radius: 10px;
            padding: 10px;
            display: none;
        }
        .error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #f87171;
        }
        .success {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #34d399;
        }
    </style>
</head>
<body>
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <div class="container">
        <div class="card">
            <div class="logo">LEAFCLOUD</div>
            <div class="title">Reset Password</div>
            
            <form id="reset-form">
                <input type="hidden" id="token" value="{{TOKEN}}">
                <div class="form-group">
                    <label for="password">New Password</label>
                    <input type="password" id="password" placeholder="Enter new password" required minlength="6">
                </div>
                <div class="form-group">
                    <label for="confirm-password">Confirm Password</label>
                    <input type="password" id="confirm-password" placeholder="Confirm new password" required minlength="6">
                </div>
                <button type="submit" id="submit-btn">Update Password</button>
            </form>
            <div id="msg" class="message"></div>
        </div>
    </div>

    <script>
        const form = document.getElementById('reset-form');
        const msg = document.getElementById('msg');
        const submitBtn = document.getElementById('submit-btn');

        function showError(text) {
            msg.textContent = text;
            msg.className = 'message error';
            msg.style.display = 'block';
        }

        function showSuccess(text) {
            msg.textContent = text;
            msg.className = 'message success';
            msg.style.display = 'block';
            form.style.display = 'none';
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const token = document.getElementById('token').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm-password').value;

            if (password !== confirmPassword) {
                showError("Passwords do not match.");
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = 'Updating...';

            try {
                const response = await fetch('/api/v1/auth/reset-password', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ token, new_password: password })
                });
                
                const data = await response.json();
                if (response.ok) {
                    showSuccess("Password successfully updated! You may now close this page.");
                } else {
                    showError(data.detail || "Failed to reset password.");
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Update Password';
                }
            } catch (err) {
                showError("Network error. Please try again.");
                submitBtn.disabled = false;
                submitBtn.textContent = 'Update Password';
            }
        });
    </script>
</body>
</html>"""

ERROR_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Invalid Token | LeafCloud</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
        }
        body {
            background: radial-gradient(circle at 10% 20%, rgb(18, 20, 36) 0%, rgb(9, 10, 15) 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            position: relative;
        }
        .container {
            z-index: 10;
            width: 100%;
            max-width: 420px;
            padding: 20px;
        }
        .card {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            color: #fff;
            text-align: center;
        }
        .logo {
            font-size: 28px;
            font-weight: 800;
            background: linear-gradient(135deg, #ef4444 0%, #f59e0b 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        .title {
            font-size: 20px;
            font-weight: 600;
            color: #f3f4f6;
            margin-bottom: 12px;
        }
        .desc {
            color: #9ca3af;
            font-size: 16px;
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">ACCESS EXPIRED</div>
            <div class="title">Link Invalid or Expired</div>
            <div class="desc">{{ERROR}}</div>
        </div>
    </div>
</body>
</html>"""

@router.get("/reset-password", response_class=HTMLResponse)
def get_reset_password_page(token: str, db: Session = Depends(get_db)):
    """Serves the password reset HTML form page."""
    from app.models.password_reset import PasswordResetToken
    db_reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.is_used == False
    ).first()

    if not db_reset:
        return HTMLResponse(
            status_code=400,
            content=ERROR_PAGE_HTML.replace("{{ERROR}}", "This reset link is invalid or has already been used.")
        )
    
    expires_at = db_reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        return HTMLResponse(
            status_code=400,
            content=ERROR_PAGE_HTML.replace("{{ERROR}}", "This reset link has expired. Please request a new password reset.")
        )

    return HTMLResponse(content=RESET_FORM_HTML.replace("{{TOKEN}}", token))

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password endpoint. Consumes reset token and updates password."""
    from app.models.password_reset import PasswordResetToken
    db_reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == request.token,
        PasswordResetToken.is_used == False
    ).first()

    if not db_reset:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
    
    expires_at = db_reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired reset token")

    user = db.query(User).filter(User.email == db_reset.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User associated with token not found")

    # Update password
    user.hashed_password = security.get_password_hash(request.new_password)
    db_reset.is_used = True

    # Revoke all active refresh sessions to force re-authentication
    db.query(security.RefreshToken).filter(
        security.RefreshToken.user_id == user.id
    ).update({security.RefreshToken.is_revoked: True}, synchronize_session=False)

    db.commit()
    return {"status": "success", "message": "Password has been successfully reset."}

@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(request: TokenRefreshRequest, db: Session = Depends(get_db)):
    """Refresh the access token using a valid refresh token (Refresh Token Rotation)."""
    db_refresh = db.query(security.RefreshToken).filter(
        security.RefreshToken.token == request.refresh_token,
        security.RefreshToken.is_revoked == False
    ).first()

    if not db_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    
    # Check expiry
    expires_at = db_refresh.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        db_refresh.is_revoked = True
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired refresh token")
    
    # Retrieve user
    user = db.query(User).filter(User.id == db_refresh.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    # Revoke the old refresh token (rotation)
    db_refresh.is_revoked = True
    db.commit()
    
    # Generate new access and refresh token pair
    access_token = security.create_access_token(data={"sub": user.email, "user_id": user.id})
    new_refresh_token = security.create_refresh_token(db=db, user_id=user.id)
    
    return {
        "status": "success",
        "token": access_token,
        "refresh_token": new_refresh_token,
        "message": "Token refreshed successfully"
    }

@router.post("/logout")
def logout(
    request: LogoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(security.get_current_user),
    token: str = Depends(security.oauth2_scheme)
):
    """Log out a user, blacklist their current access token, and revoke their refresh token."""
    try:
        payload = security.jwt.decode(token, security.settings.SECRET_KEY, algorithms=[security.settings.ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")
    except security.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if jti and exp:
        # Check if already blacklisted to prevent constraint errors
        existing = db.query(security.TokenBlacklist).filter(security.TokenBlacklist.jti == jti).first()
        if not existing:
            # Convert epoch timestamp to timezone-aware datetime
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            db_blacklist = security.TokenBlacklist(jti=jti, expires_at=exp_datetime)
            db.add(db_blacklist)
    
    # Revoke the specific refresh token
    db_refresh = db.query(security.RefreshToken).filter(
        security.RefreshToken.token == request.refresh_token
    ).first()
    if db_refresh:
        db_refresh.is_revoked = True
    
    db.commit()
    return {"status": "success", "message": "Successfully logged out"}
