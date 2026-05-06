"""
backend/auth/utils.py
──────────────────────
Password hashing, JWT creation/decoding, OTP generation, email sending.
"""
from __future__ import annotations

import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import bcrypt
import jwt

from backend.config import (
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    JWT_ALGORITHM,
    JWT_EXPIRE_DAYS,
    JWT_SECRET,
    SMTP_HOST,
    SMTP_PORT,
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


# ── Email ─────────────────────────────────────────────────────────────────────

def send_otp_email(to_email: str, name: str, otp: str) -> None:
    """Send a styled HTML OTP email via Gmail SMTP."""
    msg            = MIMEMultipart("alternative")
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = to_email
    msg["Subject"] = "Your AutoApply AI Verification Code"

    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#1a1a2e;border-radius:16px;
                    border:1px solid #2d2d4e;overflow:hidden">
        <tr>
          <td style="background:linear-gradient(135deg,#7c3aed,#2563eb);
                     padding:24px 32px;text-align:center">
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;
                       letter-spacing:1px">AutoApply AI</h1>
            <p style="margin:4px 0 0;color:rgba(255,255,255,.75);font-size:13px">
              Email Verification
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="margin:0 0 8px;color:#e2e8f0;font-size:16px">
              Hi <strong>{name}</strong>,
            </p>
            <p style="margin:0 0 24px;color:#94a3b8;font-size:14px">
              Use the code below to verify your email address.
              It expires in <strong style="color:#e2e8f0">5 minutes</strong>.
            </p>
            <div style="background:#0f0f1a;border:2px solid #7c3aed;
                        border-radius:12px;padding:20px;text-align:center;
                        margin-bottom:24px">
              <span style="font-size:40px;font-weight:800;letter-spacing:12px;
                           color:#a78bfa;font-family:monospace">{otp}</span>
            </div>
            <p style="margin:0;color:#64748b;font-size:12px;text-align:center">
              If you didn't request this, you can safely ignore this email.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()  # Re-identify after TLS
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to send OTP email: {e}")
        raise e
