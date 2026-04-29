"""
backend/auth/routes.py
───────────────────────
FastAPI router — all /api/auth/* endpoints.
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
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


# ── Simple in-memory rate limiter ─────────────────────────────────────────────

class _RateLimiter:
    """Sliding-window rate limiter keyed by arbitrary string (e.g. IP or email)."""

    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self._max    = max_calls
        self._window = window_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)
        self._lock   = threading.Lock()

    def check(self, key: str) -> None:
        """Raise HTTP 429 if the key has exceeded the rate limit."""
        now = time.monotonic()
        with self._lock:
            bucket = self._calls[key]
            # Drop timestamps outside the window
            self._calls[key] = [t for t in bucket if now - t < self._window]
            if len(self._calls[key]) >= self._max:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please wait and try again.",
                )
            self._calls[key].append(now)


# 10 login/signup attempts per IP per 15 minutes
_login_limiter  = _RateLimiter(max_calls=10, window_seconds=900)
# 3 OTP sends per email per 10 minutes
_otp_limiter    = _RateLimiter(max_calls=3,  window_seconds=600)
# 10 OTP verify attempts per IP per 10 minutes (per-OTP brute-force is in service.py)
_verify_limiter = _RateLimiter(max_calls=10, window_seconds=600)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Auth dependency ───────────────────────────────────────────────────────────

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
def signup(req: SignupRequest, request: Request):
    _login_limiter.check(_client_ip(request))
    return service.signup(
        req.first_name, req.last_name, req.email, req.phone, req.password
    )


@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(req: VerifyOtpRequest, request: Request):
    _verify_limiter.check(_client_ip(request))
    return service.verify_otp(req.email, req.otp_code)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request):
    _login_limiter.check(_client_ip(request))
    return service.login(req.email, req.password)


@router.post("/resend-otp")
def resend_otp(req: ResendOtpRequest, request: Request):
    _otp_limiter.check(req.email)
    return service.resend_otp(req.email)


# ── Protected endpoints ───────────────────────────────────────────────────────

@router.get("/me", response_model=UserInfo)
def me(user: dict = Depends(get_current_user)):
    db_user = service.get_user_by_id(int(user["sub"]))
    return {
        "user_id":     db_user["id"],
        "first_name":  db_user["first_name"],
        "last_name":   db_user["last_name"],
        "email":       db_user["email"],
        "role":        db_user["role"],
        "has_profile": bool(db_user.get("data_folder")),
    }


@router.delete("/account")
def delete_account(user: dict = Depends(get_current_user)):
    """
    Permanently delete the authenticated user's account.
    Removes: user row, OTP history, applied_jobs (CASCADE), and data folder from disk.
    The client must clear its JWT after receiving 200.
    """
    service.delete_account(int(user["sub"]))
    return {"message": "Account deleted successfully."}
