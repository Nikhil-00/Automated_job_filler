"""
backend/api/admin.py
─────────────────────
Admin portal endpoints.

POST  /api/admin/login                      — login → JWT
GET   /api/admin/companies                  — list company requests
PATCH /api/admin/companies/{id}/status      — approve / reject
  On approve: auto-generate credentials, store hashed password, email company
"""
from __future__ import annotations

import logging
import re
import secrets
import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.config import (
    ADMIN_PASSWORD,
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    JWT_ALGORITHM,
    JWT_SECRET,
    SMTP_HOST,
    SMTP_PORT,
)
from backend.database import get_connection

logger = logging.getLogger(__name__)

router  = APIRouter(prefix="/api/admin", tags=["admin"])
_bearer = HTTPBearer()

_ADMIN_JWT_EXPIRE_HOURS = 12


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _create_admin_jwt() -> str:
    payload = {
        "sub":  "admin",
        "role": "admin",
        "exp":  datetime.now(timezone.utc) + timedelta(hours=_ADMIN_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _get_admin_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "admin":
            raise ValueError("Not admin")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token.")


# ── Credential generator ──────────────────────────────────────────────────────

def _generate_credentials(officer_name: str, company_name: str, phone: str) -> tuple[str, str]:
    """
    Returns (email, plaintext_password).
    The plaintext is shown once in the approval email; only the hash is stored.
    """
    first = re.sub(r"[^a-zA-Z]", "", officer_name.strip().split()[0])
    slug  = re.sub(r"[^a-z0-9]", "", company_name.lower())[:20]
    email = f"{first.lower()}.{slug}@autofill.com"

    digits = re.sub(r"\D", "", phone)
    last4  = digits[-4:] if len(digits) >= 4 else digits.zfill(4)
    # Add a random suffix so each credential set is unique even with same name+phone
    rand   = secrets.token_hex(3).upper()
    password = f"{first.capitalize()}_{last4}_{rand}"

    return email, password


def _make_unique_email(base_email: str, cur) -> str:
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM company_requests WHERE assigned_email = %s",
        (base_email,),
    )
    row = cur.fetchone()
    count = row[0] if isinstance(row, tuple) else row["cnt"]
    if count == 0:
        return base_email

    local, domain = base_email.split("@")
    counter = 2
    while True:
        candidate = f"{local}{counter}@{domain}"
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM company_requests WHERE assigned_email = %s",
            (candidate,),
        )
        row = cur.fetchone()
        c = row[0] if isinstance(row, tuple) else row["cnt"]
        if c == 0:
            return candidate
        counter += 1


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ── Email sender ──────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            s.send_message(msg)
    except Exception as e:
        logger.error(f"SMTP failed to {to}: {e}")
        raise e


def _send_email_background(to: str, subject: str, html: str) -> None:
    def _send():
        try:
            _send_email(to, subject, html)
            logger.info("Approval email sent to %s", to)
        except Exception as e:
            logger.error("Email failed to %s: %s", to, e)
    threading.Thread(target=_send, daemon=True).start()


def _credential_email_html(
    officer_name: str,
    company_name: str,
    assigned_email: str,
    temp_password: str,
) -> str:
    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#1a1a2e;border-radius:16px;
                    border:1px solid #2d2d4e;overflow:hidden">
        <tr>
          <td style="background:linear-gradient(135deg,#166534,#16a34a);
                     padding:24px 32px;text-align:center">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">AutoApply AI</h1>
            <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:13px">
              Company Portal — Account Approved
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="margin:0 0 8px;color:#e2e8f0;font-size:16px">
              Dear <strong>{officer_name}</strong>,
            </p>
            <p style="margin:0 0 20px;color:#94a3b8;font-size:14px">
              Your company <strong style="color:#e2e8f0">{company_name}</strong> has been
              <span style="color:#4ade80;font-weight:600">approved</span> on AutoApply AI.
              Below are your one-time credentials. Please change your password after first login.
            </p>
            <table width="100%" cellpadding="12" cellspacing="0"
                   style="background:#0f0f1a;border-radius:12px;
                          border:1px solid #166534;margin-bottom:24px">
              <tr>
                <td style="color:#86efac;font-size:13px;font-weight:600;
                           border-bottom:1px solid #1a2e1a;width:110px">
                  Email
                </td>
                <td style="color:#e2e8f0;font-size:14px;font-family:monospace;
                           border-bottom:1px solid #1a2e1a">
                  {assigned_email}
                </td>
              </tr>
              <tr>
                <td style="color:#86efac;font-size:13px;font-weight:600">
                  Temp Password
                </td>
                <td style="color:#e2e8f0;font-size:14px;font-family:monospace;
                           letter-spacing:2px">
                  {temp_password}
                </td>
              </tr>
            </table>
            <p style="margin:0 0 8px;color:#f59e0b;font-size:13px">
              ⚠ Change your password immediately after your first login.
            </p>
            <p style="margin:0;color:#64748b;font-size:12px">
              Questions? Contact us at
              <a href="mailto:{EMAIL_ADDRESS}" style="color:#4ade80">{EMAIL_ADDRESS}</a>.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


# ── Pydantic models ───────────────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    email:    str
    password: str


class StatusUpdate(BaseModel):
    status: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
def admin_login(req: AdminLoginRequest):
    if req.email != EMAIL_ADDRESS or req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return {"token": _create_admin_jwt(), "message": "Welcome, Admin."}


@router.get("/companies")
def list_companies(
    status: str = "all",
    _: dict    = Depends(_get_admin_user),
):
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        if status != "all":
            cur.execute(
                "SELECT * FROM company_requests WHERE status=%s ORDER BY created_at DESC",
                (status,),
            )
        else:
            cur.execute("SELECT * FROM company_requests ORDER BY created_at DESC")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        for k in ("created_at", "otp_expires_at"):
            if r.get(k) and isinstance(r[k], datetime):
                r[k] = r[k].isoformat()
        r.pop("otp_code", None)
        r.pop("assigned_password", None)  # never expose password hash to frontend

    return {"companies": rows, "total": len(rows)}


@router.patch("/companies/{company_id}/status")
def update_company_status(
    company_id: int,
    body: StatusUpdate,
    _: dict = Depends(_get_admin_user),
):
    new_status = body.status
    if new_status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status.")

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    temp_password: str | None = None
    try:
        cur.execute(
            "SELECT * FROM company_requests WHERE id = %s",
            (company_id,),
        )
        company = cur.fetchone()
        cur.fetchall()
        if not company:
            raise HTTPException(status_code=404, detail="Company request not found.")

        assigned_email    = company.get("assigned_email")

        if new_status == "approved" and not assigned_email:
            base_email, temp_password = _generate_credentials(
                company["officer_name"],
                company["company_name"],
                company["phone"],
            )
            cur2 = conn.cursor()
            assigned_email = _make_unique_email(base_email, cur2)
            cur2.close()

            hashed_password = _hash_password(temp_password)
            cur.execute(
                "UPDATE company_requests SET status=%s, assigned_email=%s, assigned_password=%s WHERE id=%s",
                (new_status, assigned_email, hashed_password, company_id),
            )
        else:
            cur.execute(
                "UPDATE company_requests SET status=%s WHERE id=%s",
                (new_status, company_id),
            )

        conn.commit()
    finally:
        cur.close()
        conn.close()

    if new_status == "approved" and assigned_email and temp_password:
        _send_email_background(
            company["email"],
            "AutoApply AI — Your Company Account is Approved",
            _credential_email_html(
                company["officer_name"],
                company["company_name"],
                assigned_email,
                temp_password,
            ),
        )

    return {
        "message":       f"Status updated to {new_status}.",
        "assigned_email": assigned_email,
    }
