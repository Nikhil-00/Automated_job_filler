"""
backend/auth/service.py
────────────────────────
Business logic for signup, OTP verification, login.
All DB operations go through mysql.connector.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from backend.database import get_connection
from backend.auth.utils import (
    create_jwt,
    generate_otp,
    hash_password,
    send_otp_email,
    verify_password,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _send_fresh_otp(cursor, conn, email: str, first_name: str) -> None:
    """Invalidate old OTPs for this email, create a new one, and send it."""
    otp     = generate_otp()
    expires = datetime.utcnow() + timedelta(minutes=5)

    cursor.execute(
        "UPDATE otp_codes SET used=TRUE WHERE email=%s AND used=FALSE",
        (email,),
    )
    cursor.execute(
        "INSERT INTO otp_codes (email, otp_code, expires_at) VALUES (%s, %s, %s)",
        (email, otp, expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    try:
        send_otp_email(email, first_name, otp)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to send verification email: {str(e)}. Please check your SMTP settings."
        )


# ── Auth operations ───────────────────────────────────────────────────────────

def signup(
    first_name: str,
    last_name:  str,
    email:      str,
    phone:      str,
    password:   str,
) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, is_verified, first_name FROM user_credentials WHERE email=%s",
            (email,),
        )
        existing = cursor.fetchone()

        if existing:
            if existing["is_verified"]:
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered. Please log in.",
                )
            # Unverified → just resend OTP
            _send_fresh_otp(cursor, conn, email, existing["first_name"])
            return {"message": "Verification code resent to your email."}

        hashed = hash_password(password)
        cursor.execute(
            """INSERT INTO user_credentials
               (first_name, last_name, email, phone, password_hash)
               VALUES (%s, %s, %s, %s, %s)""",
            (first_name, last_name, email, phone, hashed),
        )
        conn.commit()
        _send_fresh_otp(cursor, conn, email, first_name)
        return {"message": "Account created! Check your email for the verification code."}
    finally:
        cursor.close()
        conn.close()


_MAX_OTP_ATTEMPTS = 5


def verify_otp(email: str, otp_code: str) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch the latest unused OTP for this email regardless of code value
        cursor.execute(
            """SELECT * FROM otp_codes
               WHERE email=%s AND used=FALSE
               ORDER BY created_at DESC LIMIT 1""",
            (email,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=400, detail="Invalid verification code.")

        # Brute-force guard: too many wrong attempts → invalidate the OTP
        attempts = (row.get("attempt_count") or 0)
        if attempts >= _MAX_OTP_ATTEMPTS:
            cursor.execute("UPDATE otp_codes SET used=TRUE WHERE id=%s", (row["id"],))
            conn.commit()
            raise HTTPException(
                status_code=429,
                detail="Too many incorrect attempts. Please request a new code.",
            )

        if row["otp_code"] != otp_code:
            cursor.execute(
                "UPDATE otp_codes SET attempt_count=attempt_count+1 WHERE id=%s",
                (row["id"],),
            )
            conn.commit()
            raise HTTPException(status_code=400, detail="Invalid verification code.")

        # MySQL returns datetime without tzinfo; compare as naive UTC
        now = datetime.utcnow()
        if now > row["expires_at"]:
            raise HTTPException(
                status_code=400,
                detail="Code has expired. Please request a new one.",
            )

        cursor.execute("UPDATE otp_codes SET used=TRUE WHERE id=%s", (row["id"],))
        cursor.execute(
            "UPDATE user_credentials SET is_verified=TRUE WHERE email=%s", (email,)
        )
        conn.commit()

        cursor.execute("SELECT * FROM user_credentials WHERE email=%s", (email,))
        user  = cursor.fetchone()
        token = create_jwt(user["id"], user["email"], user["role"])

        return {
            "token":       token,
            "user_id":     user["id"],
            "first_name":  user["first_name"],
            "last_name":   user["last_name"],
            "email":       user["email"],
            "role":        user["role"],
            "has_profile": bool(user.get("data_folder")),
        }
    finally:
        cursor.close()
        conn.close()


def login(email: str, password: str) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM user_credentials WHERE email=%s", (email,)
        )
        user = cursor.fetchone()

        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if not user["is_verified"]:
            raise HTTPException(
                status_code=403,
                detail="Email not verified. Please check your inbox.",
            )

        token = create_jwt(user["id"], user["email"], user["role"])
        return {
            "token":       token,
            "user_id":     user["id"],
            "first_name":  user["first_name"],
            "last_name":   user["last_name"],
            "email":       user["email"],
            "role":        user["role"],
            "has_profile": bool(user.get("data_folder")),
        }
    finally:
        cursor.close()
        conn.close()


def resend_otp(email: str) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT first_name, is_verified FROM user_credentials WHERE email=%s",
            (email,),
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Email not found.")
        if user["is_verified"]:
            raise HTTPException(status_code=400, detail="Email already verified.")

        _send_fresh_otp(cursor, conn, email, user["first_name"])
        return {"message": "New verification code sent."}
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id: int) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM user_credentials WHERE id=%s", (user_id,)
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return user
    finally:
        cursor.close()
        conn.close()


def set_user_data_folder(user_id: int, folder_name: str) -> None:
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE user_credentials SET data_folder=%s WHERE id=%s",
            (folder_name, user_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_account(user_id: int) -> None:
    """
    Permanently delete a user account and all associated data.
    Steps:
      1. Fetch email + data_folder from DB.
      2. Delete the user's data folder from disk (CV, profile, PDF, etc.).
      3. Delete all OTP codes for this email.
      4. Delete the user row — ON DELETE CASCADE removes applied_jobs automatically.
    """
    import shutil
    from pathlib import Path
    from backend.config import USER_DATA_DIR

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT email, data_folder FROM user_credentials WHERE id=%s",
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        # ── 1. Remove data folder from disk ───────────────────────────────────
        if user.get("data_folder"):
            folder = Path(USER_DATA_DIR) / user["data_folder"]
            if folder.exists():
                shutil.rmtree(folder)

        # ── 2. Delete OTP codes (keyed by email, not user_id) ─────────────────
        cursor.execute("DELETE FROM otp_codes WHERE email=%s", (user["email"],))

        # ── 3. Delete the user row (CASCADE removes applied_jobs) ─────────────
        cursor.execute("DELETE FROM user_credentials WHERE id=%s", (user_id,))

        conn.commit()
    finally:
        cursor.close()
        conn.close()

def forgot_password(email: str) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT first_name FROM user_credentials WHERE email=%s", (email,)
        )
        user = cursor.fetchone()
        if not user:
            # For security, we don't reveal if the email exists.
            # But the requirement says "mail send to his email", so we should only send if it exists.
            return {"message": "If this email is registered, you will receive a verification code."}

        _send_fresh_otp(cursor, conn, email, user["first_name"])
        return {"message": "Verification code sent to your email."}
    finally:
        cursor.close()
        conn.close()


def reset_password(email: str, otp_code: str, new_password: str) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Verify OTP
        cursor.execute(
            """SELECT * FROM otp_codes
               WHERE email=%s AND used=FALSE
               ORDER BY created_at DESC LIMIT 1""",
            (email,),
        )
        row = cursor.fetchone()

        if not row or row["otp_code"] != otp_code:
            raise HTTPException(status_code=400, detail="Invalid verification code.")

        if datetime.utcnow() > row["expires_at"]:
            raise HTTPException(status_code=400, detail="Code has expired.")

        # Update password
        hashed = hash_password(new_password)
        cursor.execute(
            "UPDATE user_credentials SET password_hash=%s WHERE email=%s",
            (hashed, email),
        )
        # Invalidate OTP
        cursor.execute("UPDATE otp_codes SET used=TRUE WHERE id=%s", (row["id"],))
        conn.commit()

        return {"message": "Password reset successfully. You can now log in."}
    finally:
        cursor.close()
        conn.close()
