"""
backend/auth/routes.py
───────────────────────
FastAPI router — all /api/auth/* endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth import service
from backend.auth.models import (
    AuthResponse,
    LoginRequest,
    ResendOtpRequest,
    SignupRequest,
    UserInfo,
    VerifyOtpRequest,
)
from backend.auth.utils import decode_jwt

router  = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """FastAPI dependency — decode JWT and return payload dict."""
    try:
        return decode_jwt(creds.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.post("/signup")
def signup(req: SignupRequest):
    """Register a new Job Seeker account and send OTP to their email."""
    return service.signup(
        req.first_name, req.last_name, req.email, req.phone, req.password
    )


@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(req: VerifyOtpRequest):
    """Verify the 6-digit code and return a JWT on success."""
    return service.verify_otp(req.email, req.otp_code)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Log in with email + password and return a JWT."""
    return service.login(req.email, req.password)


@router.post("/resend-otp")
def resend_otp(req: ResendOtpRequest):
    """Resend the verification OTP to the given email."""
    return service.resend_otp(req.email)


# ── Protected endpoints ───────────────────────────────────────────────────────

@router.get("/me", response_model=UserInfo)
def me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile info."""
    db_user = service.get_user_by_id(int(user["sub"]))
    return {
        "user_id":     db_user["id"],
        "first_name":  db_user["first_name"],
        "last_name":   db_user["last_name"],
        "email":       db_user["email"],
        "role":        db_user["role"],
        "has_profile": bool(db_user.get("data_folder")),
    }
