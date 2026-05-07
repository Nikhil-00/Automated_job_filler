"""
backend/auth/utils.py
──────────────────────
Password hashing, JWT creation/decoding, OTP generation, email sending.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from backend.config import (
    JWT_ALGORITHM,
    JWT_EXPIRE_DAYS,
    JWT_SECRET,
)


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── OTP ───────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_jwt(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub":   str(user_id),
        "email": email,
        "role":  role,
        "exp":   datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── Email (Resend Migration) ──────────────────────────────────────────────────

def send_otp_email(to_email: str, name: str, otp: str) -> None:
    """Wrapper that calls the new EmailService."""
    from backend.services.email_service import send_otp_email_v2
    send_otp_email_v2(to_email, name, otp)
