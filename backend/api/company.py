"""
backend/api/company.py
───────────────────────
Company portal endpoints.

POST /api/company/signup           — submit signup + send OTP
POST /api/company/verify-otp       — verify OTP → notify admin
POST /api/company/resend-otp       — resend OTP
POST /api/company/login            — login with assigned credentials → JWT
GET  /api/company/applicants       — list applicants for this company [auth]
GET  /api/company/cv/{user_id}     — download applicant CV             [auth]
"""
from __future__ import annotations

import json as _json
import logging
import re
import secrets
import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import io
import uuid

import bcrypt
import jwt
import pdfplumber
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

_log = logging.getLogger(__name__)

# Discriminatory filter guard — direct topics and proxy patterns
_PROHIBITED_RE = re.compile(
    r"\b(age|born|birth.?year|gender|sex(?:ual)?|religion|religious|"
    r"church|temple|mosque|married|marital|spouse|husband|wife|"
    r"pregnant|pregnancy|disabl\w*|caste|race|nationalit\w*|"
    r"ethnic\w*|divorce\w*|"
    r"graduated.before|class.of.19\d\d|born.before|"
    r"female.only|male.only|men.only|women.only|ladies.only|"
    r"general.category|unreserved.category|"
    r"fair.skin|complexion|height|weight|appearance|looks)\b"
    r"|(?<!\w)(obc|sc|st)(?!\w)",
    re.IGNORECASE,
)

from backend.config import (
    ADMIN_PASSWORD,
    EMAIL_ADDRESS,
    EMAIL_PASSWORD,
    JWT_ALGORITHM,
    JWT_SECRET,
    SMTP_HOST,
    SMTP_PORT,
    USER_DATA_DIR,
)
from backend.database import get_connection


class ApplicantActionRequest(BaseModel):
    action: str  # "shortlist" | "reject"


class CandidateChatRequest(BaseModel):
    message:         str
    history:         list[dict] = []       # [{"role": "user"|"assistant", "content": "..."}]
    application_id:  str | None = None
    job_title:       str | None = None
    job_posting_id:  str | None = None


class AiScoreRequest(BaseModel):
    application_id: str
    user_id:        int
    job_title:      str | None = None
    job_posting_id: str | None = None


class PortalAiScoreRequest(BaseModel):
    application_id: str                   # job_applications.id
    user_id:        int
    job_posting_id: str | None = None
    job_title:      str | None = None


class AgenticChatRequest(BaseModel):
    message:       str
    job_id:        str
    history:       list[dict] = []
    session_state: dict       = {}


class SendEmailRequest(BaseModel):
    candidate_id: int
    job_id:       str
    email_type:   str   # shortlist | interview_invite | rejection | offer


_COMPANY_JWT_EXPIRE_HOURS = 24 * 7
_bearer = HTTPBearer()


def _create_company_jwt(
    company_id:   int,
    email:        str,
    company_name: str,
    officer_name: str = "",
) -> str:
    payload = {
        "sub":          str(company_id),
        "email":        email,
        "company_name": company_name,
        "officer_name": officer_name,
        "role":         "company",
        "exp":          datetime.now(timezone.utc) + timedelta(hours=_COMPANY_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_company_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "company":
            raise ValueError("Not a company token")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired company token.")

router = APIRouter(prefix="/api/company", tags=["company"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)


from backend.auth.utils import send_email_robust

def _send_email(to: str, subject: str, html: str) -> None:
    send_email_robust(to, subject, html)


def _otp_email_html(officer_name: str, company_name: str, otp: str) -> str:
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
          <td style="background:linear-gradient(135deg,#ca8a04,#eab308);
                     padding:24px 32px;text-align:center">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">AutoApply AI</h1>
            <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:13px">
              Company Portal — Email Verification
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="margin:0 0 8px;color:#e2e8f0;font-size:16px">
              Hi <strong>{officer_name}</strong>,
            </p>
            <p style="margin:0 0 4px;color:#94a3b8;font-size:14px">
              Thank you for registering <strong style="color:#e2e8f0">{company_name}</strong>.
            </p>
            <p style="margin:0 0 24px;color:#94a3b8;font-size:14px">
              Use the code below to verify your email. It expires in
              <strong style="color:#e2e8f0">10 minutes</strong>.
            </p>
            <div style="background:#0f0f1a;border:2px solid #eab308;
                        border-radius:12px;padding:20px;text-align:center;
                        margin-bottom:24px">
              <span style="font-size:40px;font-weight:800;letter-spacing:12px;
                           color:#fbbf24;font-family:monospace">{otp}</span>
            </div>
            <p style="margin:0;color:#64748b;font-size:12px;text-align:center">
              If you didn't request this, please ignore this email.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _admin_notification_html(company_name: str, officer_name: str, email: str, phone: str) -> str:
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
          <td style="background:linear-gradient(135deg,#7c3aed,#2563eb);
                     padding:24px 32px;text-align:center">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">AutoApply AI</h1>
            <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:13px">
              New Company Signup Request
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="margin:0 0 20px;color:#e2e8f0;font-size:16px;font-weight:600">
              A new company has completed email verification:
            </p>
            <table width="100%" cellpadding="8" cellspacing="0"
                   style="background:#0f0f1a;border-radius:10px;border:1px solid #2d2d4e">
              <tr>
                <td style="color:#94a3b8;font-size:13px;width:140px">Company Name</td>
                <td style="color:#e2e8f0;font-size:13px;font-weight:600">{company_name}</td>
              </tr>
              <tr style="border-top:1px solid #2d2d4e">
                <td style="color:#94a3b8;font-size:13px">Officer Name</td>
                <td style="color:#e2e8f0;font-size:13px">{officer_name}</td>
              </tr>
              <tr style="border-top:1px solid #2d2d4e">
                <td style="color:#94a3b8;font-size:13px">Email</td>
                <td style="color:#e2e8f0;font-size:13px">{email}</td>
              </tr>
              <tr style="border-top:1px solid #2d2d4e">
                <td style="color:#94a3b8;font-size:13px">Phone</td>
                <td style="color:#e2e8f0;font-size:13px">{phone}</td>
              </tr>
            </table>
            <p style="margin:20px 0 0;color:#64748b;font-size:12px;text-align:center">
              Log in to the Admin Portal to review this request.
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

class SignupRequest(BaseModel):
    company_name: str
    officer_name: str
    email:        str
    phone:        str
    password:     str


class PostJobRequest(BaseModel):
    title:           str
    description:     str
    skills:          list[str] = []
    location:        str = ""
    work_mode:       str = "onsite"   # onsite | remote | hybrid
    job_type:        str = "full-time"
    experience_min:  int = 0
    experience_max:  int = 5
    salary_min:      int | None = None
    salary_max:      int | None = None
    salary_currency: str = "INR"
    openings:        int = 1


class JobStatusRequest(BaseModel):
    is_active: bool


class PortalApplicantActionRequest(BaseModel):
    action: str  # shortlist | reject


class LoginRequest(BaseModel):
    email:    str
    password: str


class VerifyOtpRequest(BaseModel):
    email:    str
    otp_code: str


class ResendOtpRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email:        str
    otp_code:     str
    new_password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup")
def company_signup(req: SignupRequest):
    """
    Accept company signup details, send OTP to their email.
    If email already exists but unverified — resend OTP.
    If already verified — reject with 409.
    """
    # Hash password immediately
    hashed_pw = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id, is_otp_verified FROM company_requests WHERE email = %s ORDER BY id DESC LIMIT 1",
            (req.email,),
        )
        existing = cur.fetchone()

        if existing and existing["is_otp_verified"]:
            raise HTTPException(
                status_code=409,
                detail="This email has already been registered. Please contact support.",
            )

        otp     = _generate_otp()
        expires = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        if existing and not existing["is_otp_verified"]:
            cur.execute(
                """UPDATE company_requests 
                   SET company_name=%s, officer_name=%s, phone=%s, otp_code=%s, 
                       otp_expires_at=%s, assigned_email=%s, assigned_password=%s 
                   WHERE id=%s""",
                (req.company_name, req.officer_name, req.phone, otp, expires, req.email, hashed_pw, existing["id"]),
            )
        else:
            cur.execute(
                """INSERT INTO company_requests
                   (company_name, officer_name, email, phone, otp_code, otp_expires_at, assigned_email, assigned_password)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (req.company_name, req.officer_name, req.email, req.phone, otp, expires, req.email, hashed_pw),
            )

        conn.commit()
    finally:
        cur.close()
        conn.close()

    # Send OTP email (outside DB transaction)
    try:
        _send_email(
            req.email,
            "AutoApply AI — Company Verification Code",
            _otp_email_html(req.officer_name, req.company_name, otp),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP email: {e}")

    return {"message": "OTP sent to your email. Please verify within 10 minutes."}


@router.post("/verify-otp")
def company_verify_otp(req: VerifyOtpRequest):
    """
    Verify OTP → mark company as verified → notify admin via email.
    """
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT * FROM company_requests WHERE email = %s ORDER BY id DESC LIMIT 1",
            (req.email,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Email not found. Please sign up first.")

        if row["is_otp_verified"]:
            raise HTTPException(status_code=400, detail="Email already verified.")

        if row["otp_code"] != req.otp_code:
            raise HTTPException(status_code=400, detail="Invalid OTP code.")

        now = datetime.utcnow()
        if now > row["otp_expires_at"]:
            raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

        # Auto-approve: Mark as verified and approved
        cur.execute(
            """UPDATE company_requests
               SET is_otp_verified=TRUE, otp_code=NULL, status='approved'
               WHERE id=%s""",
            (row["id"],),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {
        "message":      "Email verified. Your portal is ready — you can now log in with your password.",
        "auto_approved": True,
    }


@router.post("/resend-otp")
def company_resend_otp(req: ResendOtpRequest):
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT * FROM company_requests WHERE email = %s ORDER BY id DESC LIMIT 1",
            (req.email,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Email not found.")
        if row["is_otp_verified"]:
            raise HTTPException(status_code=400, detail="Email already verified.")

        otp     = _generate_otp()
        expires = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "UPDATE company_requests SET otp_code=%s, otp_expires_at=%s WHERE id=%s",
            (otp, expires, row["id"]),
        )
        conn.commit()
        company = dict(row)
    finally:
        cur.close()
        conn.close()

    try:
        _send_email(
            req.email,
            "AutoApply AI — New Verification Code",
            _otp_email_html(company["officer_name"], company["company_name"], otp),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {e}")

    return {"message": "New OTP sent to your email."}


@router.post("/login")
def company_login(req: LoginRequest):
    """
    Login with assigned credentials (assigned_email + assigned_password).
    Returns a JWT on success.
    """
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT * FROM company_requests WHERE assigned_email = %s ORDER BY id DESC LIMIT 1",
            (req.email,),
        )
        company = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not company:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if company["status"] != "approved":
        raise HTTPException(status_code=403, detail="Your account is pending approval. Please wait for admin confirmation.")

    try:
        password_ok = bcrypt.checkpw(req.password.encode(), company["assigned_password"].encode())
    except Exception:
        password_ok = False
    if not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = _create_company_jwt(
        company["id"],
        company["assigned_email"],
        company["company_name"],
        company.get("officer_name") or "",
    )
    return {
        "token":        token,
        "company_name": company["company_name"],
        "officer_name": company["officer_name"],
        "email":        company["assigned_email"],
    }


@router.post("/forgot-password")
def company_forgot_password(req: ForgotPasswordRequest):
    """
    Send OTP for password reset if the company is already approved/active.
    """
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id, officer_name, company_name FROM company_requests WHERE assigned_email = %s AND status='approved' LIMIT 1",
            (req.email,),
        )
        row = cur.fetchone()
        if not row:
            # Silence failure for security
            return {"message": "If this email is registered, you will receive a reset code."}

        otp     = _generate_otp()
        expires = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        cur.execute(
            "UPDATE company_requests SET otp_code=%s, otp_expires_at=%s WHERE id=%s",
            (otp, expires, row["id"]),
        )
        conn.commit()
        company = dict(row)
    finally:
        cur.close()
        conn.close()

    try:
        _send_email(
            req.email,
            "AutoApply AI — Company Password Reset Code",
            _otp_email_html(company["officer_name"], company["company_name"], otp),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {e}")

    return {"message": "Reset code sent to your email."}


@router.post("/reset-password")
def company_reset_password(req: ResetPasswordRequest):
    """
    Verify reset OTP and update assigned_password.
    """
    # Hash new password
    hashed = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id, otp_code, otp_expires_at FROM company_requests WHERE assigned_email = %s AND status='approved' LIMIT 1",
            (req.email,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found.")

        if not row["otp_code"] or row["otp_code"] != req.otp_code:
            raise HTTPException(status_code=400, detail="Invalid reset code.")

        if datetime.utcnow() > row["otp_expires_at"]:
            raise HTTPException(status_code=400, detail="Reset code has expired.")

        # Update password and clear OTP
        cur.execute(
            "UPDATE company_requests SET assigned_password=%s, otp_code=NULL WHERE id=%s",
            (hashed, row["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"message": "Password reset successfully. You can now log in."}


# ── CV download ───────────────────────────────────────────────────────────────

@router.get("/cv/{user_id}")
def download_cv(
    user_id: int,
    company: dict = Depends(get_company_user),
):
    """Stream the applicant's uploaded CV file."""
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT first_name, last_name, data_folder FROM user_credentials WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user or not user.get("data_folder"):
        raise HTTPException(status_code=404, detail="CV not found.")

    cv_dir = USER_DATA_DIR / user["data_folder"]
    for pattern in ["uploaded_cv.pdf", "*.pdf", "*.docx", "*.doc"]:
        matches = list(cv_dir.glob(pattern))
        if matches:
            f    = matches[0]
            name = f"{user['first_name']}_{user['last_name']}_CV{f.suffix}"
            return FileResponse(str(f), media_type="application/octet-stream", filename=name)

    raise HTTPException(status_code=404, detail="CV file not found.")


# ── Shortlist / Reject applicant ──────────────────────────────────────────────

def _shortlist_email_html(
    candidate_name: str,
    job_title: str,
    company_name: str,
    officer_name: str,
    officer_email: str,
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
              Profile Shortlisted
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="margin:0 0 12px;color:#e2e8f0;font-size:16px">
              Dear <strong>{candidate_name}</strong>,
            </p>
            <p style="margin:0 0 20px;color:#94a3b8;font-size:14px;line-height:1.6">
              Congratulations! Your profile has been
              <span style="color:#4ade80;font-weight:600">shortlisted</span>
              for the role of
              <strong style="color:#e2e8f0">{job_title}</strong>
              by <strong style="color:#e2e8f0">{company_name}</strong>.
            </p>

            <table width="100%" cellpadding="10" cellspacing="0"
                   style="background:#0f0f1a;border-radius:10px;
                          border:1px solid #166534;margin-bottom:24px">
              <tr>
                <td style="color:#86efac;font-size:13px;font-weight:600;
                           border-bottom:1px solid #1a2e1a;width:130px">
                  Reviewed by
                </td>
                <td style="color:#e2e8f0;font-size:13px;
                           border-bottom:1px solid #1a2e1a">
                  {officer_name}
                </td>
              </tr>
              <tr>
                <td style="color:#86efac;font-size:13px;font-weight:600">Contact</td>
                <td style="color:#e2e8f0;font-size:13px">
                  <a href="mailto:{officer_email}"
                     style="color:#4ade80;text-decoration:none">{officer_email}</a>
                </td>
              </tr>
            </table>

            <p style="margin:0;color:#94a3b8;font-size:13px;line-height:1.6">
              The recruiter will reach out to you directly at the above email
              with further details about the next steps.
            </p>
            <p style="margin:16px 0 0;color:#64748b;font-size:12px">
              Best of luck!<br/>— The AutoApply AI Team
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _credentials_email_html(officer_name: str, company_name: str, email: str, password: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 16px">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#1a1a2e;border-radius:16px;border:1px solid #2d2d4e;overflow:hidden">
        <tr>
          <td style="background:linear-gradient(135deg,#7c3aed,#2563eb);padding:24px 32px;text-align:center">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700">AutoApply AI</h1>
            <p style="margin:4px 0 0;color:rgba(255,255,255,.8);font-size:13px">Your Company Portal is Ready</p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px">
            <p style="margin:0 0 8px;color:#e2e8f0;font-size:16px">Hi <strong>{officer_name}</strong>,</p>
            <p style="margin:0 0 20px;color:#94a3b8;font-size:14px">
              <strong style="color:#e2e8f0">{company_name}</strong> has been approved on AutoApply AI.
              Use the credentials below to log in and start posting jobs.
            </p>
            <table width="100%" cellpadding="10" cellspacing="0"
                   style="background:#0f0f1a;border-radius:10px;border:1px solid #2d2d4e;margin-bottom:24px">
              <tr>
                <td style="color:#94a3b8;font-size:13px;width:110px">Login Email</td>
                <td style="color:#e2e8f0;font-size:13px;font-weight:600">{email}</td>
              </tr>
              <tr style="border-top:1px solid #2d2d4e">
                <td style="color:#94a3b8;font-size:13px">Password</td>
                <td style="color:#e2e8f0;font-size:13px;font-weight:600;letter-spacing:1px">{password}</td>
              </tr>
            </table>
            <p style="margin:0;color:#64748b;font-size:12px;text-align:center">
              Please change your password after your first login. Keep these credentials safe.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _send_email_background(to: str, subject: str, html: str) -> None:
    def _send():
        try:
            _send_email(to, subject, html)
            _log.info("Email sent to %s", to)
        except Exception as e:
            _log.error("Email failed to %s: %s", to, e)
    threading.Thread(target=_send, daemon=True).start()


def _extract_cv_text(data_folder: str) -> str:
    """Return plain text from the candidate's uploaded PDF CV, or empty string."""
    cv_dir = USER_DATA_DIR / data_folder
    for pattern in ["uploaded_cv.pdf", "*.pdf"]:
        matches = list(cv_dir.glob(pattern))
        if matches:
            try:
                with pdfplumber.open(str(matches[0])) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
            except Exception as exc:
                _log.warning("CV text extraction failed: %s", exc)
    return ""


def _load_profile(data_folder: str) -> dict:
    """Return the candidate's profile.json as a dict, or empty dict."""
    path = USER_DATA_DIR / data_folder / "profile.json"
    if path.exists():
        try:
            return _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── Candidate AI match score ──────────────────────────────────────────────────

@router.post("/candidate/ai-score")
def compute_ai_score(
    body: AiScoreRequest,
    company: dict = Depends(get_company_user),
):
    """
    Compute an AI match score (0-100) between a candidate and a job.
    Result is cached in applied_jobs.ai_match_score so Groq is only
    called once per application — subsequent calls return instantly from DB.
    """
    # ── 1. Return cached score if available ───────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT ai_match_score, ai_score_reason FROM applied_jobs WHERE id = %s",
            (body.application_id,),
        )
        cached = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if cached and cached.get("ai_match_score") is not None:
        return {
            "score":  cached["ai_match_score"],
            "reason": cached.get("ai_score_reason") or "",
            "cached": True,
        }

    # ── 2. Load candidate CV + profile ────────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT data_folder FROM user_credentials WHERE id = %s",
            (body.user_id,),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    data_folder  = user.get("data_folder") or ""
    cv_text      = _extract_cv_text(data_folder) if data_folder else ""
    profile      = _load_profile(data_folder)    if data_folder else {}
    profile_text = "\n".join(f"{k}: {v}" for k, v in profile.items() if v)

    if not cv_text and not profile_text:
        return {"score": 50, "reason": "Insufficient candidate data to compute a score.", "cached": False}

    jd_text  = ""
    jd_title = body.job_title or ""

    # ── 4. Ask Groq to score the match ────────────────────────────────────────
    from backend.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        return {"score": 50, "reason": "AI scoring not configured.", "cached": False}

    jd_block = f"JOB DESCRIPTION:\n{jd_text[:3000]}" if jd_text else f"JOB TITLE: {jd_title or 'Not specified'}\n(Full JD not available)"

    prompt = f"""You are a senior technical recruiter. Score how well the candidate fits the job on a scale of 0 to 100.

{jd_block}

CANDIDATE PROFILE:
{profile_text or "Not available"}

CANDIDATE CV:
{cv_text[:3000] or "Not available"}

Return ONLY valid JSON with exactly two keys:
{{"score": <integer 0-100>, "reason": "<one concise sentence explaining the score>"}}"""

    try:
        from groq import Groq as _Groq
        client   = _Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a senior technical recruiter. Return only valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        result = _json.loads(response.choices[0].message.content)
        score  = max(0, min(100, int(result.get("score", 50))))
        reason = str(result.get("reason", ""))[:500]
    except Exception as exc:
        _log.error("AI score error for %s: %s", body.application_id, exc)
        return {"score": 50, "reason": "Scoring failed — please retry.", "cached": False}

    # ── 5. Cache result in DB ─────────────────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE applied_jobs SET ai_match_score = %s, ai_score_reason = %s WHERE id = %s",
            (score, reason, body.application_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"score": score, "reason": reason, "cached": False}


# ── Candidate AI chat ─────────────────────────────────────────────────────────

@router.post("/candidate/{user_id}/chat")
def chat_with_candidate(
    user_id: int,
    body: CandidateChatRequest,
    company: dict = Depends(get_company_user),
):
    """
    Recruiter asks the AI a question about a specific candidate.
    Answers are strictly grounded on the candidate's CV and profile data.
    Prohibited discriminatory questions are blocked before reaching Groq.
    """
    # Guard: reject discriminatory questions immediately
    if _PROHIBITED_RE.search(body.message):
        return {
            "reply": (
                "I'm not able to answer questions about personal characteristics "
                "such as age, gender, religion, or marital status. "
                "Please ask about the candidate's professional qualifications and experience."
            )
        }

    # Fetch candidate data folder
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT first_name, last_name, data_folder FROM user_credentials WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    data_folder    = user.get("data_folder") or ""
    candidate_name = f"{user['first_name']} {user['last_name']}"

    cv_text = _extract_cv_text(data_folder) if data_folder else ""
    profile = _load_profile(data_folder)    if data_folder else {}

    profile_text = "\n".join(
        f"{k}: {v}" for k, v in profile.items() if v
    ) if profile else "No profile data available."

    # ── Fetch Job Description ─────────────────────────────────────────────────
    jd_title = body.job_title or ""
    jd_text  = ""

    # LinkedIn-automation-scraped description stored in applied_jobs
    if body.application_id:
        conn2 = get_connection()
        cur2  = conn2.cursor(dictionary=True)
        try:
            cur2.execute(
                "SELECT title, description FROM applied_jobs WHERE id = %s",
                (body.application_id,),
            )
            job_row = cur2.fetchone()
            if job_row:
                if not jd_title:
                    jd_title = job_row.get("title") or ""
                jd_text = job_row.get("description") or ""
        finally:
            cur2.close()
            conn2.close()

    # Fallback: World Wide portal job — JD stored directly in job_postings
    if not jd_text and body.job_posting_id:
        conn_p = get_connection()
        cur_p  = conn_p.cursor(dictionary=True)
        try:
            cur_p.execute(
                "SELECT title, description FROM job_postings WHERE id = %s",
                (body.job_posting_id,),
            )
            jp_row = cur_p.fetchone()
            if jp_row:
                if not jd_title:
                    jd_title = jp_row.get("title") or ""
                jd_text = jp_row.get("description") or ""
        finally:
            cur_p.close()
            conn_p.close()

    jd_section = (
        f"\n--- JOB DESCRIPTION ({jd_title}) ---\n{jd_text}\n--- END JOB DESCRIPTION ---"
        if jd_text else
        f"\n--- JOB APPLIED FOR ---\n{jd_title or 'Not specified'}\n(Full JD not available for this application.)"
    )

    system_prompt = f"""You are a professional recruitment assistant helping a recruiter at {company.get("company_name", "a company")} evaluate a job applicant.

The applicant's name is {candidate_name}.

STRICT RULES — you must follow these without exception:
1. Answer ONLY from the candidate data provided below. Do not invent, infer, or assume anything not explicitly stated.
2. If the answer is not in the data, say exactly: "I don't have that information in {candidate_name}'s profile."
3. If a question is unrelated to professional background, skills, experience, education, or job suitability, say: "I can only answer questions about the candidate's professional qualifications."
4. Never speculate about compensation expectations, availability, or willingness to relocate unless stated in the data.
5. When assessing candidate fit for the role, compare their CV/profile against the Job Description provided.
6. Keep answers concise — 2 to 4 sentences maximum.

--- CANDIDATE PROFILE ---
{profile_text}

--- CANDIDATE CV ---
{cv_text if cv_text else "No CV text could be extracted."}
--- END OF CANDIDATE DATA ---
{jd_section}"""

    # Build message list (cap history at 10 turns to control token usage)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for turn in body.history[-10:]:
        role    = turn.get("role", "")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": body.message})

    from backend.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured (GROQ_API_KEY missing).")

    from groq import Groq as _Groq
    client = _Groq(api_key=GROQ_API_KEY)

    def _stream_groq():
        try:
            stream = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.1,
                max_tokens=512,
                stream=True,
            )
            for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield f"data: {_json.dumps({'text': token})}\n\n"
        except Exception as exc:
            _log.error("Groq stream error for candidate %d: %s", user_id, exc)
            yield f"data: {_json.dumps({'error': 'AI service error. Please try again.'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream_groq(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",   # disable nginx buffering if behind a proxy
        },
    )


# ── JD Upload → AI auto-fill ──────────────────────────────────────────────────

@router.post("/parse-jd")
async def parse_jd(
    file:    UploadFile = File(...),
    company: dict = Depends(get_company_user),
):
    """Upload a JD (PDF or text) → AI extracts structured fields for the job posting form."""
    content = await file.read()

    # Extract raw text
    if file.filename and file.filename.lower().endswith(".pdf"):
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        except Exception:
            text = content.decode("utf-8", errors="ignore")
    else:
        text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from the uploaded file.")

    from backend.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured.")

    prompt = f"""Extract structured fields from this job description and return ONLY valid JSON.

JOB DESCRIPTION:
{text[:4000]}

Return JSON with exactly these keys:
{{
  "title": "<job title>",
  "description": "<full job description text, preserve details>",
  "skills": ["skill1", "skill2"],
  "experience_min": <integer years>,
  "experience_max": <integer years>,
  "salary_min": <integer or null>,
  "salary_max": <integer or null>,
  "location": "<city or remote>",
  "work_mode": "<onsite|remote|hybrid>",
  "job_type": "<full-time|part-time|contract|internship|freelance>"
}}"""

    try:
        from groq import Groq as _Groq
        client = _Groq(api_key=GROQ_API_KEY)
        resp   = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a job description parser. Return only valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        result = _json.loads(resp.choices[0].message.content)
    except Exception as exc:
        _log.error("JD parse error: %s", exc)
        raise HTTPException(status_code=500, detail="AI parsing failed. Please try again.")

    # Sanitise
    def _int_or_none(v):
        try: return int(v) if v is not None else None
        except: return None

    return {
        "title":          str(result.get("title") or ""),
        "description":    str(result.get("description") or text[:3000]),
        "skills":         [s for s in (result.get("skills") or []) if isinstance(s, str)],
        "experience_min": _int_or_none(result.get("experience_min")) or 0,
        "experience_max": _int_or_none(result.get("experience_max")) or 5,
        "salary_min":     _int_or_none(result.get("salary_min")),
        "salary_max":     _int_or_none(result.get("salary_max")),
        "location":       str(result.get("location") or ""),
        "work_mode":      str(result.get("work_mode") or "onsite"),
        "job_type":       str(result.get("job_type") or "full-time"),
    }


# ── Parse JD from plain text ─────────────────────────────────────────────────

class ParseJdTextRequest(BaseModel):
    text: str


@router.post("/parse-jd-text")
def parse_jd_text(
    body:    ParseJdTextRequest,
    company: dict = Depends(get_company_user),
):
    """Parse a job description pasted as plain text → same structured fields as /parse-jd."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided.")
    if len(text) < 30:
        raise HTTPException(status_code=400, detail="Text is too short to be a job description.")

    from backend.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured.")

    prompt = f"""Extract structured fields from this job description and return ONLY valid JSON.

JOB DESCRIPTION:
{text[:4000]}

Return JSON with exactly these keys:
{{
  "title": "<job title>",
  "description": "<full job description text, preserve details>",
  "skills": ["skill1", "skill2"],
  "experience_min": <integer years>,
  "experience_max": <integer years>,
  "salary_min": <integer or null>,
  "salary_max": <integer or null>,
  "location": "<city or remote>",
  "work_mode": "<onsite|remote|hybrid>",
  "job_type": "<full-time|part-time|contract|internship|freelance>"
}}"""

    try:
        from groq import Groq as _Groq
        client = _Groq(api_key=GROQ_API_KEY)
        resp   = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a job description parser. Return only valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        result = _json.loads(resp.choices[0].message.content)
    except Exception as exc:
        _log.error("JD text parse error: %s", exc)
        raise HTTPException(status_code=500, detail="AI parsing failed. Please try again.")

    def _int_or_none(v):
        try: return int(v) if v is not None else None
        except: return None

    return {
        "title":          str(result.get("title") or ""),
        "description":    str(result.get("description") or text[:3000]),
        "skills":         [s for s in (result.get("skills") or []) if isinstance(s, str)],
        "experience_min": _int_or_none(result.get("experience_min")) or 0,
        "experience_max": _int_or_none(result.get("experience_max")) or 5,
        "salary_min":     _int_or_none(result.get("salary_min")),
        "salary_max":     _int_or_none(result.get("salary_max")),
        "location":       str(result.get("location") or ""),
        "work_mode":      str(result.get("work_mode") or "onsite"),
        "job_type":       str(result.get("job_type") or "full-time"),
    }


# ── Job CRUD (non-Big4 recruiters) ────────────────────────────────────────────

@router.post("/jobs")
def post_job(body: PostJobRequest, company: dict = Depends(get_company_user)):
    """Create a new job posting (World Wide portal)."""
    company_id   = int(company["sub"])
    company_name = company.get("company_name", "")
    job_id       = str(uuid.uuid4())
    created_at   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO job_postings
                (id, company_id, company_name, title, description, skills,
                 location, work_mode, job_type, experience_min, experience_max,
                 salary_min, salary_max, salary_currency, openings, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                job_id, company_id, company_name,
                body.title, body.description, _json.dumps(body.skills),
                body.location, body.work_mode, body.job_type,
                body.experience_min, body.experience_max,
                body.salary_min, body.salary_max, body.salary_currency,
                body.openings, created_at,
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    # Trigger candidate matching + Job Vectorization in background
    def _background_tasks():
        # 1. Generate AI vector for the job itself
        try:
            from backend.utils.vector_store import upsert_job_vector
            upsert_job_vector(job_id, body.title, body.description)
        except Exception as e:
            _log.error("Job vectorization failed: %s", e)

        # 2. Match existing candidates to this new job
        try:
            from backend.services.candidate_matching import run_matching
            run_matching(job_id)
        except Exception as e:
            _log.error("Initial candidate matching failed: %s", e)

    threading.Thread(target=_background_tasks, daemon=True).start()

    return {"job_id": job_id, "message": "Job posted successfully."}


@router.get("/jobs")
def list_my_jobs(
    search:  str = "",
    company: dict = Depends(get_company_user),
):
    """List all jobs posted by this company."""
    company_id = int(company["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        if search:
            like = f"%{search}%"
            cur.execute(
                """
                SELECT jp.id, jp.title, jp.location, jp.work_mode, jp.job_type,
                       jp.experience_min, jp.experience_max,
                       jp.salary_min, jp.salary_max, jp.salary_currency,
                       jp.openings, jp.is_active, jp.created_at, jp.skills,
                       (SELECT COUNT(*) FROM job_applications WHERE job_id = jp.id) +
                       (SELECT COUNT(*) FROM candidate_job_matches WHERE job_id = jp.id) AS applicant_count
                FROM job_postings jp
                WHERE jp.company_id = %s AND (jp.title LIKE %s OR jp.description LIKE %s)
                ORDER BY jp.created_at DESC
                """,
                (company_id, like, like),
            )
        else:
            cur.execute(
                """
                SELECT jp.id, jp.title, jp.location, jp.work_mode, jp.job_type,
                       jp.experience_min, jp.experience_max,
                       jp.salary_min, jp.salary_max, jp.salary_currency,
                       jp.openings, jp.is_active, jp.created_at, jp.skills,
                       (SELECT COUNT(*) FROM job_applications WHERE job_id = jp.id) +
                       (SELECT COUNT(*) FROM candidate_job_matches WHERE job_id = jp.id) AS applicant_count
                FROM job_postings jp
                WHERE jp.company_id = %s
                ORDER BY jp.created_at DESC
                """,
                (company_id,),
            )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        try:
            r["skills"] = _json.loads(r["skills"]) if r.get("skills") else []
        except Exception:
            r["skills"] = []

    return {"jobs": rows, "total": len(rows)}


@router.patch("/jobs/{job_id}/status")
def update_job_status(
    job_id: str,
    body:   JobStatusRequest,
    company: dict = Depends(get_company_user),
):
    """Toggle a job posting active/inactive."""
    company_id = int(company["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM job_postings WHERE id = %s AND company_id = %s",
            (job_id, company_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")
        cur.execute(
            "UPDATE job_postings SET is_active = %s WHERE id = %s",
            (body.is_active, job_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"message": "ok", "is_active": body.is_active}


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id:  str,
    company: dict = Depends(get_company_user),
):
    """Delete a job posting (cascades to its applications)."""
    company_id = int(company["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM job_postings WHERE id = %s AND company_id = %s",
            (job_id, company_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")
        cur.execute("DELETE FROM job_postings WHERE id = %s", (job_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"message": "deleted"}


# ── Auto-matched candidates for a job posting ─────────────────────────────────

@router.get("/jobs/{job_id}/matched-candidates")
def get_matched_candidates(
    job_id:  str,
    company: dict = Depends(get_company_user),
):
    """Return auto-matched candidates ranked by AI score for a specific job posting."""
    company_id = int(company["sub"])

    # Verify job belongs to this company
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM job_postings WHERE id = %s AND company_id = %s",
            (job_id, company_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")

        cur.execute(
            """
            SELECT
                cjm.id              AS match_id,
                cjm.ai_score,
                cjm.ai_reasoning,
                cjm.shortlist_status,
                cjm.matched_at,
                uc.id               AS user_id,
                uc.first_name,
                uc.last_name,
                uc.email,
                uc.phone,
                uc.data_folder,
                cp.current_job_title,
                cp.years_experience,
                cp.expected_ctc
            FROM candidate_job_matches cjm
            JOIN user_credentials uc ON uc.id = cjm.user_id
            LEFT JOIN candidate_profile cp ON cp.user_id = cjm.user_id
            WHERE cjm.job_id = %s
            ORDER BY cjm.ai_score DESC
            """,
            (job_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("matched_at"), datetime):
            r["matched_at"] = r["matched_at"].isoformat()
        r["has_cv"] = bool(r.get("data_folder"))
        r.pop("data_folder", None)

    return {"candidates": rows, "total": len(rows)}


@router.patch("/jobs/{job_id}/matched-candidates/{user_id}/status")
def update_matched_candidate_status(
    job_id:  str,
    user_id: int,
    body:    ApplicantActionRequest,
    company: dict = Depends(get_company_user),
):
    """Shortlist or reject an auto-matched candidate."""
    if body.action not in ("shortlist", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'shortlist' or 'reject'.")

    company_id = int(company["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM job_postings WHERE id = %s AND company_id = %s",
            (job_id, company_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")

        new_status = "shortlisted" if body.action == "shortlist" else "rejected"
        cur.execute(
            "UPDATE candidate_job_matches SET shortlist_status = %s WHERE job_id = %s AND user_id = %s",
            (new_status, job_id, user_id),
        )
        conn.commit()

        if body.action == "shortlist":
            cur.execute(
                "SELECT first_name, last_name, email FROM user_credentials WHERE id = %s",
                (user_id,),
            )
            cand = cur.fetchone()
            cur.execute("SELECT title FROM job_postings WHERE id = %s", (job_id,))
            job  = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if body.action == "shortlist" and cand and job:
        _send_email_background(
            cand["email"],
            f"Your profile has been shortlisted by {company.get('company_name', '')}",
            _shortlist_email_html(
                f"{cand['first_name']} {cand['last_name']}",
                job["title"],
                company.get("company_name", ""),
                company.get("officer_name", ""),
                company.get("email", ""),
            ),
        )

    return {"message": "ok", "action": body.action}


@router.post("/jobs/{job_id}/re-match")
def re_run_matching(job_id: str, company: dict = Depends(get_company_user)):
    """Re-trigger auto-matching for an existing job posting."""
    company_id = int(company["sub"])
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM job_postings WHERE id = %s AND company_id = %s AND is_active = TRUE",
            (job_id, company_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")
    finally:
        cur.close()
        conn.close()

    def _match():
        from backend.services.candidate_matching import run_matching
        run_matching(job_id)
    threading.Thread(target=_match, daemon=True).start()

    return {"message": "Matching started in background."}


# ── Portal applicants (non-Big4 recruiters) ───────────────────────────────────

@router.get("/portal-applicants")
def get_portal_applicants(
    job_id:     str = "",
    search:     str = "",
    status:     str = "",        # "" | applied | shortlisted | rejected
    sort_by:    str = "recent",  # recent | score_high | score_low | name
    score_tier: str = "",        # "" | high | medium | low
    has_cv:     str = "",        # "" | yes | no
    company: dict = Depends(get_company_user),
):
    """Return applicants who applied to this company's World Wide job postings."""
    company_id = int(company["sub"])

    conditions = ["jp.company_id = %s"]
    params: list = [company_id]

    if job_id:
        conditions.append("jp.id = %s")
        params.append(job_id)
    if search:
        like = f"%{search}%"
        conditions.append(
            "(jp.title LIKE %s OR uc.first_name LIKE %s OR uc.last_name LIKE %s OR uc.email LIKE %s)"
        )
        params += [like, like, like, like]
    if status:
        conditions.append("ja.status = %s")
        params.append(status)
    if score_tier == "high":
        conditions.append("ja.ai_match_score >= 70")
    elif score_tier == "medium":
        conditions.append("ja.ai_match_score >= 45 AND ja.ai_match_score < 70")
    elif score_tier == "low":
        conditions.append("(ja.ai_match_score IS NULL OR ja.ai_match_score < 45)")
    if has_cv == "yes":
        conditions.append("uc.data_folder IS NOT NULL AND uc.data_folder != ''")
    elif has_cv == "no":
        conditions.append("(uc.data_folder IS NULL OR uc.data_folder = '')")

    _PORTAL_SORT = {
        "recent":     "ja.applied_at DESC",
        "score_high": "ja.ai_match_score IS NULL, ja.ai_match_score DESC",
        "score_low":  "ja.ai_match_score IS NOT NULL, ja.ai_match_score ASC",
        "name":       "uc.first_name ASC, uc.last_name ASC",
    }
    order_clause = _PORTAL_SORT.get(sort_by, "ja.applied_at DESC")
    where = " AND ".join(conditions)

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        # 1. Manual portal applicants
        cur.execute(
            f"""
            SELECT
                ja.id              AS application_id,
                ja.applied_at,
                ja.status,
                ja.ai_match_score,
                ja.ai_score_reason,
                jp.id              AS job_posting_id,
                jp.title           AS applied_for,
                jp.location,
                uc.id              AS user_id,
                uc.first_name,
                uc.last_name,
                uc.email,
                uc.phone,
                uc.data_folder
            FROM job_applications ja
            JOIN job_postings     jp ON jp.id  = ja.job_id
            JOIN user_credentials uc ON uc.id  = ja.user_id
            WHERE {where}
            ORDER BY {order_clause}
            """,
            params,
        )
        rows = cur.fetchall()

        # 2. Auto-matched candidates
        m_conds:  list[str] = ["jp.company_id = %s"]
        m_params: list      = [company_id]
        if job_id:
            m_conds.append("cjm.job_id = %s")
            m_params.append(job_id)
        if search:
            like = f"%{search}%"
            m_conds.append("(uc.first_name LIKE %s OR uc.last_name LIKE %s OR uc.email LIKE %s)")
            m_params += [like, like, like]
        if status:
            m_conds.append("cjm.shortlist_status = %s")
            m_params.append("pending" if status == "applied" else status)
        if score_tier == "high":
            m_conds.append("cjm.ai_score >= 70")
        elif score_tier == "medium":
            m_conds.append("cjm.ai_score >= 45 AND cjm.ai_score < 70")
        elif score_tier == "low":
            m_conds.append("(cjm.ai_score IS NULL OR cjm.ai_score < 45)")
        if has_cv == "yes":
            m_conds.append("uc.data_folder IS NOT NULL AND uc.data_folder != ''")
        elif has_cv == "no":
            m_conds.append("(uc.data_folder IS NULL OR uc.data_folder = '')")

        cur.execute(
            f"""
            SELECT
                cjm.job_id           AS job_posting_id,
                cjm.matched_at       AS applied_at,
                cjm.shortlist_status AS status_raw,
                cjm.ai_score         AS ai_match_score,
                cjm.ai_reasoning     AS ai_score_reason,
                jp.title             AS applied_for,
                jp.location,
                uc.id                AS user_id,
                uc.first_name,
                uc.last_name,
                uc.email,
                uc.phone,
                uc.data_folder
            FROM candidate_job_matches cjm
            JOIN job_postings     jp ON jp.id  = cjm.job_id
            JOIN user_credentials uc ON uc.id  = cjm.user_id
            WHERE {" AND ".join(m_conds)}
            """,
            m_params,
        )
        matched = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    # Normalize manual applicants
    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        r["has_cv"]   = bool(r.get("data_folder"))
        r["is_match"] = False

    # Merge matched — skip if same user+job already applied manually
    manual_pairs = {(r["user_id"], r["job_posting_id"]) for r in rows}
    for r in matched:
        if (r["user_id"], r["job_posting_id"]) in manual_pairs:
            continue
        status_raw          = r.pop("status_raw", "pending")
        r["status"]         = "applied" if status_raw == "pending" else status_raw
        r["application_id"] = f"match_{r['user_id']}_{r['job_posting_id'][:8]}"
        r["is_match"]       = True
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        r["has_cv"] = bool(r.get("data_folder"))
        r.pop("data_folder", None)
        rows.append(r)

    # Sort merged list in Python
    if sort_by == "score_high":
        rows.sort(key=lambda x: x.get("ai_match_score") if x.get("ai_match_score") is not None else -1, reverse=True)
    elif sort_by == "score_low":
        rows.sort(key=lambda x: (x.get("ai_match_score") is not None, x.get("ai_match_score") or 0))
    elif sort_by == "name":
        rows.sort(key=lambda x: (x.get("first_name", "").lower(), x.get("last_name", "").lower()))
    else:
        rows.sort(key=lambda x: x.get("applied_at") or "", reverse=True)

    return {"applicants": rows, "total": len(rows)}


@router.patch("/portal-applicants/{app_id}/status")
def update_portal_applicant_status(
    app_id:  str,
    body:    PortalApplicantActionRequest,
    company: dict = Depends(get_company_user),
):
    """Shortlist or reject a portal job applicant."""
    if body.action not in ("shortlist", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'shortlist' or 'reject'.")

    company_id = int(company["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT ja.id, ja.status, jp.title,
                   uc.first_name, uc.last_name, uc.email AS candidate_email
            FROM job_applications ja
            JOIN job_postings     jp ON jp.id = ja.job_id
            JOIN user_credentials uc ON uc.id = ja.user_id
            WHERE ja.id = %s AND jp.company_id = %s
            """,
            (app_id, company_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")

        new_status = "shortlisted" if body.action == "shortlist" else "rejected"
        cur.execute(
            "UPDATE job_applications SET status = %s WHERE id = %s",
            (new_status, app_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    if body.action == "shortlist":
        officer_name   = company.get("officer_name", "")
        officer_email  = company.get("email", "")
        company_name   = company.get("company_name", "")
        candidate_name = f"{row['first_name']} {row['last_name']}"
        _send_email_background(
            row["candidate_email"],
            f"Your profile has been shortlisted by {company_name}",
            _shortlist_email_html(
                candidate_name, row["title"], company_name, officer_name, officer_email,
            ),
        )

    return {"message": "ok", "action": body.action}


# ── Portal AI match score (job_applications table) ────────────────────────────

@router.post("/candidate/portal-ai-score")
def compute_portal_ai_score(
    body:    PortalAiScoreRequest,
    company: dict = Depends(get_company_user),
):
    """
    Compute an AI match score for a World Wide portal application.
    JD is loaded from job_postings. Score cached in job_applications.
    """
    # ── 1. Return cached score ────────────────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT ai_match_score, ai_score_reason FROM job_applications WHERE id = %s",
            (body.application_id,),
        )
        cached = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if cached and cached.get("ai_match_score") is not None:
        return {
            "score":  cached["ai_match_score"],
            "reason": cached.get("ai_score_reason") or "",
            "cached": True,
        }

    # ── 2. Load candidate CV + profile ───────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT data_folder FROM user_credentials WHERE id = %s",
            (body.user_id,),
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    data_folder  = user.get("data_folder") or ""
    cv_text      = _extract_cv_text(data_folder) if data_folder else ""
    profile      = _load_profile(data_folder)    if data_folder else {}
    profile_text = "\n".join(f"{k}: {v}" for k, v in profile.items() if v)

    if not cv_text and not profile_text:
        return {"score": 50, "reason": "Insufficient candidate data to compute a score.", "cached": False}

    # ── 3. Load JD from job_postings ─────────────────────────────────────────
    jd_text  = ""
    jd_title = body.job_title or ""

    if body.job_posting_id:
        conn2 = get_connection()
        cur2  = conn2.cursor(dictionary=True)
        try:
            cur2.execute(
                "SELECT title, description FROM job_postings WHERE id = %s",
                (body.job_posting_id,),
            )
            jp = cur2.fetchone()
            if jp:
                jd_title = jp.get("title") or jd_title
                jd_text  = jp.get("description") or ""
        finally:
            cur2.close()
            conn2.close()

    # ── 4. Ask Groq ───────────────────────────────────────────────────────────
    from backend.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        return {"score": 50, "reason": "AI scoring not configured.", "cached": False}

    jd_block = (
        f"JOB DESCRIPTION:\n{jd_text[:3000]}"
        if jd_text else
        f"JOB TITLE: {jd_title or 'Not specified'}\n(Full JD not available)"
    )

    prompt = (
        "You are a senior technical recruiter. Score how well the candidate fits the job on a scale of 0 to 100.\n\n"
        f"{jd_block}\n\n"
        f"CANDIDATE PROFILE:\n{profile_text or 'Not available'}\n\n"
        f"CANDIDATE CV:\n{cv_text[:3000] or 'Not available'}\n\n"
        'Return ONLY valid JSON with exactly two keys:\n'
        '{"score": <integer 0-100>, "reason": "<one concise sentence explaining the score>"}'
    )

    try:
        from groq import Groq as _Groq
        client   = _Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a senior technical recruiter. Return only valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        result = _json.loads(response.choices[0].message.content)
        score  = max(0, min(100, int(result.get("score", 50))))
        reason = str(result.get("reason", ""))[:500]
    except Exception as exc:
        _log.error("Portal AI score error for %s: %s", body.application_id, exc)
        return {"score": 50, "reason": "Scoring failed — please retry.", "cached": False}

    # ── 5. Cache in job_applications ─────────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE job_applications SET ai_match_score = %s, ai_score_reason = %s WHERE id = %s",
            (score, reason, body.application_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {"score": score, "reason": reason, "cached": False}


# ═══════════════════════════════════════════════════════════════════════════════
# AGENTIC RECRUITER ASSISTANT
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re_mod

# ── Date / experience helpers ─────────────────────────────────────────────────

def _parse_work_date(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if s.lower() in ("present", "current", "now", ""):
        return None
    for fmt in ("%b %Y", "%B %Y", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _total_experience_years(work_experience: list) -> float:
    total = 0.0
    now   = datetime.now()
    for exp in work_experience:
        start = _parse_work_date(exp.get("start_date") or "")
        if start is None:
            continue
        end_str    = exp.get("end_date") or ""
        is_current = (
            exp.get("currently_working", False)
            or end_str.lower() in ("present", "current", "now", "")
        )
        end    = now if is_current else (_parse_work_date(end_str) or now)
        months = (end.year - start.year) * 12 + (end.month - start.month)
        total += max(0, months)
    return round(total / 12, 1)


# ── CV data loader ────────────────────────────────────────────────────────────

def _load_cv_data(data_folder: str, cache: dict | None = None) -> dict:
    """
    Merge profile.json + cv_data.json into one flat dict.
    profile.json  — summary fields: current_salary, expected_salary, notice_period,
                    years_of_experience, current_job_title, current_company, etc.
    cv_data.json  — detailed structured fields: work_experience, education,
                    skills {technical/soft}, projects, certifications, achievements.
    cv_data wins on key conflicts (it is more structured).
    Pass a shared cache dict to avoid re-reading the same files in one request.
    """
    if not data_folder:
        return {}
    if cache is not None and data_folder in cache:
        return cache[data_folder]

    base = USER_DATA_DIR / data_folder

    profile: dict = {}
    profile_path = base / "profile.json"
    if profile_path.exists():
        try:
            profile = _json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    cv: dict = {}
    cv_path = base / "cv_data.json"
    if cv_path.exists():
        try:
            cv = _json.loads(cv_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # profile is the base; cv_data fields overwrite on conflict (cv is more structured)
    result = {**profile, **cv}

    if cache is not None:
        cache[data_folder] = result
    return result


# ── Match scoring ─────────────────────────────────────────────────────────────

def _score_candidate(cv: dict, job: dict) -> tuple[int, str]:
    """Score a candidate against a job using structured cv_data.json. Returns (0-100, reason)."""
    score   = 0
    reasons: list[str] = []

    job_title  = (job.get("title") or "").lower()
    job_desc   = (job.get("description") or "").lower()
    job_skills = [s.lower().strip() for s in (job.get("skills") or [])]
    exp_min    = int(job.get("experience_min") or 0)
    exp_max    = int(job.get("experience_max") or 99)
    job_loc    = (job.get("location") or "").lower().strip()

    tech_skills = [s.lower().strip() for s in (cv.get("skills") or {}).get("technical") or []]
    soft_skills = [s.lower().strip() for s in (cv.get("skills") or {}).get("soft") or []]
    all_skills  = tech_skills + soft_skills

    # Skills (40 pts)
    if job_skills:
        matched     = sum(1 for js in job_skills if any(js in cs or cs in js for cs in all_skills))
        score      += int((matched / len(job_skills)) * 40)
        if matched:
            reasons.append(f"{matched}/{len(job_skills)} required skills matched")
    else:
        kw_hits = sum(1 for s in tech_skills if len(s) > 3 and s in job_desc)
        score  += min(25, kw_hits * 5)
        if kw_hits:
            reasons.append(f"{kw_hits} skill keywords in JD")

    # Experience (20 pts)
    exp_years = _total_experience_years(cv.get("work_experience") or [])
    if exp_min <= exp_years <= exp_max:
        score += 20
        reasons.append(f"{exp_years}y exp fits {exp_min}–{exp_max}y")
    elif exp_years > exp_max:
        score += 10
        reasons.append(f"overqualified ({exp_years}y)")
    elif exp_years > 0:
        score += 5

    # Location (10 pts)
    cand_loc = (cv.get("contact") or {}).get("location") or ""
    if job_loc and job_loc in cand_loc.lower():
        score += 10
        reasons.append("location match")

    # Role relevance (20 pts)
    summary     = (cv.get("summary") or "").lower()
    _stop       = {"with","that","this","have","from","they","will","your","been","also","into"}
    title_words = [w for w in _re_mod.findall(r"\b[a-z]{4,}\b", job_title) if w not in _stop]
    if title_words:
        hits   = sum(1 for w in title_words if w in summary)
        score += int((hits / len(title_words)) * 20)
        if hits:
            reasons.append("role keywords in summary")

    # Education present (10 pts)
    if cv.get("education"):
        score += 10

    score  = max(5, min(98, score))
    reason = "; ".join(reasons) if reasons else "Profile reviewed"
    return score, reason


# ── Job / candidate resolvers ─────────────────────────────────────────────────

def _resolve_job(job_id: str, company_id: int) -> dict:
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id, title, description, skills, location, "
            "experience_min, experience_max "
            "FROM job_postings WHERE id = %s AND company_id = %s",
            (job_id, company_id),
        )
        row = cur.fetchone()
        if not row:
            return {"error": "Job not found or access denied."}
        row["source"] = "portal"
        try:
            row["skills"] = _json.loads(row["skills"]) if row.get("skills") else []
        except Exception:
            row["skills"] = []
    finally:
        cur.close()
        conn.close()
    return row


def _get_candidates_for_job(job_id: str, company_id: int) -> list[dict]:
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT ja.id AS application_id, ja.user_id, ja.status, ja.applied_at,
                   uc.first_name, uc.last_name, uc.email, uc.phone, uc.data_folder
            FROM   job_applications ja
            JOIN   job_postings     jp ON jp.id = ja.job_id
            JOIN   user_credentials uc ON uc.id = ja.user_id
            WHERE  ja.job_id = %s AND jp.company_id = %s
            """,
            (job_id, company_id),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        r["is_match"] = False

    # Also include auto-matched candidates (exclude duplicates)
    applied_user_ids = {r["user_id"] for r in rows}
    conn2 = get_connection()
    cur2  = conn2.cursor(dictionary=True)
    try:
        cur2.execute(
            """
            SELECT cjm.user_id, cjm.shortlist_status AS status, cjm.matched_at AS applied_at,
                   cjm.ai_score AS ai_match_score, cjm.ai_reasoning AS ai_score_reason,
                   uc.first_name, uc.last_name, uc.email, uc.phone, uc.data_folder
            FROM candidate_job_matches cjm
            JOIN user_credentials uc ON uc.id = cjm.user_id
            WHERE cjm.job_id = %s
            """,
            (job_id,),
        )
        matched = cur2.fetchall()
    finally:
        cur2.close()
        conn2.close()

    for r in matched:
        if r["user_id"] in applied_user_ids:
            continue
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        r["application_id"] = f"match_{r['user_id']}_{job_id[:8]}"
        r["is_match"] = True
        rows.append(r)

    return rows


# ── OpenAI tool definitions ───────────────────────────────────────────────────

_AGENTIC_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_candidates",
            "description": (
                "Unified candidate tool — search, profile, and compare in one call.\n"
                "• No candidate_ids → search/rank applicants, returns summaries (max 20).\n"
                "• One candidate_id → full profile: all CV fields, salary, notice period, contact, etc.\n"
                "• Multiple candidate_ids (2–6) → side-by-side comparison of skills, salary, experience."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "query": {
                        "type": "string",
                        "description": "Name or keyword to search. Leave empty to list/rank all.",
                    },
                    "candidate_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": (
                            "Pass exactly 1 ID for a full profile. "
                            "Pass 2–6 IDs for a side-by-side comparison."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "default": 15,
                        "description": "Max results in search mode (max 20).",
                    },
                    "filters": {
                        "type": "object",
                        "properties": {
                            "min_experience_years": {"type": "number"},
                            "max_experience_years": {"type": "number"},
                            "location":             {"type": "string"},
                            "skills": {
                                "type": "array", "items": {"type": "string"},
                                "description": "Candidate must have ALL of these skills.",
                            },
                            "education_keywords": {
                                "type": "array", "items": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_email_preview",
            "description": (
                "Build an email preview for the recruiter to review BEFORE sending. "
                "Does NOT send the email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id":         {"type": "string"},
                    "candidate_id":   {"type": "integer"},
                    "email_type": {
                        "type": "string",
                        "enum": ["shortlist", "interview_invite", "rejection", "offer"],
                    },
                    "custom_message": {"type": "string"},
                },
                "required": ["job_id", "candidate_id", "email_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_application_status",
            "description": "Get the current application status for one candidate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id":       {"type": "string"},
                    "candidate_id": {"type": "integer"},
                },
                "required": ["job_id", "candidate_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": "Return full job description and metadata for the selected job.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

def _tool_get_candidates(args: dict) -> dict:
    job_id        = args["job_id"]
    query         = (args.get("query") or "").lower().strip()
    candidate_ids = [int(i) for i in (args.get("candidate_ids") or [])]
    filters       = args.get("filters") or {}
    limit         = min(int(args.get("limit") or 15), 20)
    company_id = args["_company_id"]
    cv_cache   = args.get("_cv_cache")

    job = _resolve_job(job_id, company_id)
    if "error" in job:
        return job

    candidates = _get_candidates_for_job(job_id, company_id)
    if not candidates:
        return {"candidates": [], "total": 0, "message": "No applicants for this job yet.", "mode": "search"}

    cand_map = {c["user_id"]: c for c in candidates}

    # ── Profile mode: single candidate full detail ────────────────────────────
    if len(candidate_ids) == 1:
        cand = cand_map.get(candidate_ids[0])
        if not cand:
            return {"error": "Candidate not found for this job."}
        cv = _load_cv_data(cand.get("data_folder") or "", cv_cache)
        score, reason = _score_candidate(cv, job)
        merged: dict = {k: v for k, v in cv.items() if v is not None}
        merged.update({
            "candidate_id":       cand["user_id"],
            "name":               f"{cand['first_name']} {cand['last_name']}",
            "email":              cand["email"] or (cv.get("contact") or {}).get("email") or "",
            "phone":              cand.get("phone") or (cv.get("contact") or {}).get("phone") or "",
            "application_status": cand.get("status") or "applied",
            "applied_at":         cand.get("applied_at") or "",
            "match_score":        score,
            "match_reason":       reason,
            "experience_years":   _total_experience_years(cv.get("work_experience") or []),
        })
        return {"profile": merged, "mode": "profile"}

    # ── Compare mode: 2–6 candidates side-by-side ─────────────────────────────
    if len(candidate_ids) >= 2:
        if len(candidate_ids) > 6:
            return {"error": "Maximum 6 candidates can be compared at once."}
        comparison = []
        for cid in candidate_ids:
            cand = cand_map.get(cid)
            if not cand:
                comparison.append({"candidate_id": cid, "error": "Not found for this job."})
                continue
            cv = _load_cv_data(cand.get("data_folder") or "", cv_cache)
            score, reason = _score_candidate(cv, job)
            we = cv.get("work_experience") or [{}]
            comparison.append({
                "candidate_id":        cid,
                "name":                f"{cand['first_name']} {cand['last_name']}",
                "match_score":         score,
                "match_reason":        reason,
                "experience_years":    _total_experience_years(cv.get("work_experience") or []),
                "skills_technical":    (cv.get("skills") or {}).get("technical") or [],
                "skills_soft":         (cv.get("skills") or {}).get("soft") or [],
                "education": [
                    f"{e.get('degree')} — {e.get('institution')} ({e.get('end_year','')})"
                    for e in (cv.get("education") or [])
                ],
                "current_role": (
                    f"{we[0].get('title','')} at {we[0].get('company','')}".strip(" at")
                    if we else "N/A"
                ),
                "location":            (cv.get("contact") or {}).get("location") or "",
                "status":              cand.get("status") or "applied",
                "current_salary":      cv.get("current_salary"),
                "expected_salary":     cv.get("expected_salary"),
                "notice_period":       cv.get("notice_period"),
                "years_of_experience": cv.get("years_of_experience"),
            })
        return {"comparison": comparison, "mode": "compare", "job_title": job.get("title", "")}

    # ── Search mode: filter + rank, return summaries ──────────────────────────
    min_exp      = filters.get("min_experience_years")
    max_exp      = filters.get("max_experience_years")
    location_f   = (filters.get("location") or "").lower().strip()
    req_skills   = [s.lower().strip() for s in (filters.get("skills") or [])]
    edu_keywords = [k.lower().strip() for k in (filters.get("education_keywords") or [])]

    # If a query is provided, use semantic search to find candidate IDs first
    semantic_matches: dict[int, float] = {}
    if query and not candidate_ids:
        try:
            from backend.utils.vector_store import search_candidates
            results = search_candidates(query, limit=100)
            semantic_matches = {cid: score for cid, score in results}
            _log.info("Semantic search for '%s' returned %d results", query, len(semantic_matches))
        except Exception as v_exc:
            _log.warning("Semantic search failed in tool: %s", v_exc)

    results = []
    for cand in candidates:
        user_id = cand["user_id"]
        
        # If we have semantic results, and this candidate isn't in them, skip (unless query is name match)
        full_name = f"{cand['first_name']} {cand['last_name']}".lower()
        if semantic_matches and user_id not in semantic_matches and query not in full_name:
            continue
        
        if query and not semantic_matches and query not in full_name:
            continue

        cv            = _load_cv_data(cand.get("data_folder") or "", cv_cache)
        score, reason = _score_candidate(cv, job)
        exp_years     = _total_experience_years(cv.get("work_experience") or [])

        if min_exp is not None and exp_years < min_exp:
            continue
        if max_exp is not None and exp_years > max_exp:
            continue
        if location_f:
            cand_loc = (cv.get("contact") or {}).get("location") or ""
            if location_f not in cand_loc.lower():
                continue
        if req_skills:
            tech  = [s.lower() for s in (cv.get("skills") or {}).get("technical") or []]
            soft  = [s.lower() for s in (cv.get("skills") or {}).get("soft") or []]
            avail = tech + soft
            if not all(any(rs in cs or cs in rs for cs in avail) for rs in req_skills):
                continue
        if edu_keywords:
            institutions = [e.get("institution", "").lower() for e in (cv.get("education") or [])]
            if not any(kw in inst for kw in edu_keywords for inst in institutions):
                continue

        we = cv.get("work_experience") or [{}]
        results.append({
            "candidate_id":     cand["user_id"],
            "name":             f"{cand['first_name']} {cand['last_name']}",
            "email":            cand["email"],
            "status":           cand.get("status") or "applied",
            "match_score":      score,
            "match_reason":     reason,
            "experience_years": exp_years,
            "location":         (cv.get("contact") or {}).get("location") or "",
            "current_title":    we[0].get("title", "") if we else "",
            "skills_preview":   (cv.get("skills") or {}).get("technical") or [],
            "current_salary":   cv.get("current_salary"),
            "expected_salary":  cv.get("expected_salary"),
            "notice_period":    cv.get("notice_period"),
        })

    results.sort(key=lambda x: x["match_score"], reverse=True)
    results = results[:limit]

    if query and not results:
        msg = f"No candidates named '{query}' found for this job."
    elif query and len(results) > 1:
        short_list = "\n".join(
            f"{i+1}. {r['name']} (ID:{r['candidate_id']}) — {r['match_score']}% match"
            for i, r in enumerate(results)
        )
        msg = (
            f"MULTIPLE MATCHES for '{query}':\n{short_list}\n"
            f"Ask which one, or offer to compare all."
        )
    elif results:
        msg = f"Found {len(results)} candidate(s)."
    else:
        msg = "No candidates matched the specified filters."

    return {"candidates": results, "total": len(results), "message": msg, "mode": "search"}


def _build_email_body(
    email_type: str,
    candidate_name: str,
    job_title: str,
    company_name: str,
    officer_name: str,
    officer_email: str,
    custom_message: str,
) -> tuple[str, str]:
    extra = f"\n\n{custom_message}" if custom_message else ""

    if email_type == "shortlist":
        subject = f"Your profile has been shortlisted — {job_title}"
        body    = (
            f"Dear {candidate_name},\n\n"
            f"We are pleased to inform you that your profile has been shortlisted for "
            f"{job_title} at {company_name}.\n\n"
            f"Our recruiter {officer_name} will be in touch shortly with next steps.{extra}\n\n"
            f"For queries, contact: {officer_email}\n\n"
            f"Best regards,\n{officer_name}\n{company_name}"
        )
    elif email_type == "interview_invite":
        subject = f"Interview Invitation — {job_title} at {company_name}"
        body    = (
            f"Dear {candidate_name},\n\n"
            f"We would like to invite you for an interview for {job_title} at {company_name}.\n\n"
            f"Please reply to {officer_email} to confirm your availability.{extra}\n\n"
            f"Best regards,\n{officer_name}\n{company_name}"
        )
    elif email_type == "rejection":
        subject = f"Update on your application — {job_title}"
        body    = (
            f"Dear {candidate_name},\n\n"
            f"Thank you for your interest in {job_title} at {company_name}.\n\n"
            f"After careful consideration, we have decided to move forward with other candidates "
            f"at this time.{extra}\n\n"
            f"We appreciate your interest and wish you the best in your search.\n\n"
            f"Best regards,\n{officer_name}\n{company_name}"
        )
    elif email_type == "offer":
        subject = f"Offer of Employment — {job_title} at {company_name}"
        body    = (
            f"Dear {candidate_name},\n\n"
            f"We are delighted to extend an offer for {job_title} at {company_name}.\n\n"
            f"Please reply to {officer_email} to acknowledge and confirm acceptance. "
            f"A formal offer letter will follow.{extra}\n\n"
            f"Best regards,\n{officer_name}\n{company_name}"
        )
    else:
        subject = f"Update — {job_title}"
        body    = f"Dear {candidate_name},\n\n{custom_message or ''}\n\nBest regards,\n{officer_name}\n{company_name}"

    return subject, body


def _tool_prepare_email_preview(args: dict) -> dict:
    job_id         = args["job_id"]
    candidate_id   = int(args["candidate_id"])
    email_type     = args.get("email_type") or ""
    custom_message = args.get("custom_message") or ""
    company_id     = args["_company_id"]
    company_name   = args["_company_name"]
    officer_name   = args["_officer_name"]
    officer_email  = args["_officer_email"]

    if email_type not in ("shortlist", "interview_invite", "rejection", "offer"):
        return {"error": f"Invalid email_type '{email_type}'."}

    candidates = _get_candidates_for_job(job_id, company_id)
    cand       = next((c for c in candidates if c["user_id"] == candidate_id), None)
    if not cand:
        return {"error": "Candidate not found for this job."}
    if not cand.get("email"):
        return {"error": "Candidate has no email address on file."}

    warnings: list[str] = []
    status = (cand.get("status") or "").lower()
    if status in ("rejected", "withdrawn"):
        warnings.append(f"⚠️ Candidate status is '{status}'. Proceed with caution.")

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM email_logs WHERE candidate_id=%s AND job_id=%s AND email_type=%s",
            (candidate_id, job_id, email_type),
        )
        already_sent = bool(cur.fetchone())
    finally:
        cur.close()
        conn.close()

    if already_sent:
        warnings.append(f"⚠️ A '{email_type}' email was already sent to this candidate for this job.")

    job        = _resolve_job(job_id, company_id)
    job_title  = job.get("title", "the role") if "error" not in job else "the role"
    cand_name  = f"{cand['first_name']} {cand['last_name']}"
    subject, body = _build_email_body(
        email_type, cand_name, job_title,
        company_name, officer_name, officer_email, custom_message,
    )

    return {
        "preview": {
            "candidate_id": candidate_id,
            "job_id":       job_id,
            "to_name":      cand_name,
            "to_email":     cand["email"],
            "email_type":   email_type,
            "subject":      subject,
            "body":         body,
            "warnings":     warnings,
            "already_sent": already_sent,
        }
    }


def _tool_get_application_status(args: dict) -> dict:
    job_id       = args["job_id"]
    candidate_id = int(args["candidate_id"])
    company_id   = args["_company_id"]

    candidates = _get_candidates_for_job(job_id, company_id)
    cand       = next((c for c in candidates if c["user_id"] == candidate_id), None)
    if not cand:
        return {"error": "Candidate not found for this job."}

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT email_type, sent_at FROM email_logs "
            "WHERE candidate_id = %s AND job_id = %s ORDER BY sent_at ASC",
            (candidate_id, job_id),
        )
        emails_sent = [
            {"type": r["email_type"], "sent_at": str(r["sent_at"])}
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()

    return {
        "candidate_id": candidate_id,
        "name":         f"{cand['first_name']} {cand['last_name']}",
        "status":       cand.get("status") or "applied",
        "applied_at":   cand.get("applied_at") or "",
        "emails_sent":  emails_sent,
    }


def _tool_get_job_details(args: dict) -> dict:
    job_id     = args["job_id"]
    company_id = args["_company_id"]

    job = _resolve_job(job_id, company_id)
    if "error" in job:
        return job
    job["applicant_count"] = len(_get_candidates_for_job(job_id, company_id))
    return job


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict) -> dict:
    _handlers: dict = {
        "get_candidates":         _tool_get_candidates,
        "prepare_email_preview":  _tool_prepare_email_preview,
        "get_application_status": _tool_get_application_status,
        "get_job_details":        _tool_get_job_details,
    }
    handler = _handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(args)
    except Exception as exc:
        _log.error("Tool %s failed: %s", name, exc, exc_info=True)
        return {"error": f"Tool error: {exc}"}


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_agent_system_prompt(company_name: str, job_title: str, job_id: str, officer_name: str) -> str:
    return f"""You are an expert AI recruitment assistant for {company_name}, helping {officer_name} evaluate candidates.

CURRENT JOB CONTEXT:
- Title: {job_title}
- Job ID: {job_id}
Use job_id="{job_id}" in ALL tool calls. Never ask the recruiter for a job ID.

TOOL USAGE — get_candidates handles everything about candidates:
• Search / rank / filter  → call get_candidates(job_id, query="<name or blank>", filters={{...}})
• Full profile of one     → call get_candidates(job_id, candidate_ids=[id])
• Compare 2–6 candidates  → call get_candidates(job_id, candidate_ids=[id1, id2, ...])
Do NOT call get_candidates twice to load profiles before comparing — pass the IDs directly.

SCOPE — YOU ARE A RECRUITMENT ASSISTANT ONLY:
You only answer questions about candidates, job applications, hiring decisions, and emails.
If the recruiter asks ANYTHING outside this scope — coding questions, general knowledge,
writing essays, math problems, jokes, or any other off-topic request — respond with exactly:
"I can only help with recruitment tasks such as finding candidates, comparing profiles, or sending emails."
Do NOT answer the off-topic question. Do NOT apologize at length. Just redirect in one sentence.

STRICT RULES:
1. Only use data from tool results. Never invent names, scores, or emails.
2. NAME DISAMBIGUATION — when a name search returns 2+ results:
   List them: "N. Name (ID:X) — Y% match" and ask which one.
   After recruiter picks → call get_candidates(candidate_ids=[chosen_id]) for full profile.
3. Resolve positional references ("number 2", "the first one") from the last shown list without asking again.
4. Always show match % next to candidate names. Format: "1. Name — 82% match".
5. If all candidates score below 40%, say so clearly.
6. If a job has 0 applicants, say so clearly.
7. Only call prepare_email_preview — never send directly. Wait for recruiter confirmation.
8. Before preparing an email, call get_application_status to check current status and emails already sent.
9. If get_application_status shows the email type was already sent → refuse to prepare it again. Say: "A [type] email was already sent to [name] on [date]. I cannot resend it to avoid duplicates."
10. Refuse bulk email requests — only one candidate per email action.
11. Cap comparisons at 6 candidates at a time.
12. Refuse discriminatory filters (age, gender, caste, religion, marital status, nationality). Offer skills/experience/location filters instead.

RESPONSE STYLE: Concise, professional. Numbered lists for candidates. Always include match scores."""


# ── GET /api/company/agentic-jobs ────────────────────────────────────────────

@router.get("/agentic-jobs")
def get_agentic_jobs(company: dict = Depends(get_company_user)):
    """Job list for the agentic chat job selector."""
    company_id = int(company["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT jp.id, jp.title, jp.location,
                   CASE WHEN jp.is_active=TRUE THEN 'active' ELSE 'closed' END AS status,
                   jp.created_at,
                   (SELECT COUNT(*) FROM job_applications    WHERE job_id = jp.id) +
                   (SELECT COUNT(*) FROM candidate_job_matches WHERE job_id = jp.id) AS applicant_count
            FROM   job_postings jp
            WHERE  jp.company_id = %s
            ORDER  BY jp.created_at DESC
            """,
            (company_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()

    return {"jobs": rows, "total": len(rows)}


# ── POST /api/company/agentic-chat ───────────────────────────────────────────

@router.post("/agentic-chat")
def agentic_chat(
    body:    AgenticChatRequest,
    company: dict = Depends(get_company_user),
):
    """
    Agentic recruiter assistant — GPT-4o-mini with 4 tools, streamed SSE.
    All tool calls are scoped and verified against the recruiter's company.
    """
    # Discrimination guard
    if _PROHIBITED_RE.search(body.message):
        def _refuse():
            msg = (
                "I'm not able to process requests involving personal characteristics "
                "such as age, gender, religion, caste, or marital status — "
                "this may violate fair hiring laws.\n"
                "I can filter by skills, experience level, or location instead."
            )
            yield f"data: {_json.dumps({'text': msg})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            _refuse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    company_id    = int(company["sub"])
    company_name  = company.get("company_name", "")
    officer_name  = company.get("officer_name") or company.get("email") or "Recruiter"
    officer_email = company.get("email") or ""

    job = _resolve_job(body.job_id, company_id)
    if "error" in job:
        def _err(msg=job["error"]):
            yield f"data: {_json.dumps({'error': msg})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    session_state  = body.session_state or {}
    system_content = _build_agent_system_prompt(company_name, job.get("title", ""), body.job_id, officer_name)

    last_shown = session_state.get("last_shown_candidates") or []
    if last_shown:
        ctx = "\n".join(f"{i+1}. {c['name']} (ID:{c['id']})" for i, c in enumerate(last_shown))
        system_content += f"\n\nLAST CANDIDATE LIST:\n{ctx}"

    last_discussed = session_state.get("last_discussed_candidate")
    if last_discussed:
        system_content += f"\nLAST DISCUSSED: {last_discussed['name']} (ID:{last_discussed['id']})"

    messages: list[dict] = [{"role": "system", "content": system_content}]
    for turn in body.history[-20:]:
        role    = turn.get("role", "")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": body.message})

    tool_ctx = {
        "_company_id":    company_id,
        "_company_name":  company_name,
        "_officer_name":  officer_name,
        "_officer_email": officer_email,
        "_cv_cache":      {},
    }

    from backend.config import OPENAI_API_KEY
    from openai import OpenAI as _OpenAI
    client = _OpenAI(api_key=OPENAI_API_KEY, timeout=45.0)

    def _stream():
        nonlocal messages
        updated_session = dict(session_state)

        for _iteration in range(5):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=_AGENTIC_TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=1500,
                )
            except Exception as exc:
                _log.error("OpenAI agentic error: %s", exc)
                yield f"data: {_json.dumps({'error': 'AI service error. Please try again.'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            msg = response.choices[0].message

            if not msg.tool_calls:
                yield f"data: {_json.dumps({'type': 'session_state', 'state': updated_session})}\n\n"
                for word in (msg.content or "").split(" "):
                    yield f"data: {_json.dumps({'text': word + ' '})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Append assistant message with tool calls
            messages.append({
                "role":    "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id":       tc.id,
                        "type":     "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                yield f"data: {_json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

                try:
                    args = _json.loads(tc.function.arguments)
                except _json.JSONDecodeError:
                    result = {"error": f"Malformed arguments for '{tool_name}'."}
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": _json.dumps(result)})
                    continue

                args.update(tool_ctx)
                result = _dispatch_tool(tool_name, args)

                if tool_name == "get_candidates":
                    mode = result.get("mode")
                    if mode == "search" and "candidates" in result:
                        updated_session["last_shown_candidates"] = [
                            {"id": c["candidate_id"], "name": c["name"]}
                            for c in result["candidates"]
                        ]
                    elif mode == "profile" and "profile" in result:
                        p = result["profile"]
                        cid = p.get("candidate_id")
                        if cid:
                            updated_session["last_discussed_candidate"] = {"id": cid, "name": p.get("name", "")}
                if tool_name == "get_application_status":
                    cid  = result.get("candidate_id")
                    name = result.get("name", "")
                    if cid:
                        updated_session["last_discussed_candidate"] = {"id": cid, "name": name}

                if tool_name == "prepare_email_preview" and "preview" in result:
                    yield f"data: {_json.dumps({'type': 'email_preview', 'preview': result['preview']})}\n\n"

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      _json.dumps(result),
                })

        yield f"data: {_json.dumps({'type': 'session_state', 'state': updated_session})}\n\n"
        yield f"data: {_json.dumps({'text': 'I need more steps to complete this. Try breaking your request into smaller parts (e.g. first ask for top candidates, then ask to compare specific ones).'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── POST /api/company/send-email ─────────────────────────────────────────────

@router.post("/send-email")
def send_agentic_email(
    body:    SendEmailRequest,
    company: dict = Depends(get_company_user),
):
    """
    Send an email confirmed by the recruiter after prepare_email_preview.
    Duplicate sends for the same (candidate, job, type) are rejected.
    """
    company_id    = int(company["sub"])
    company_name  = company.get("company_name", "")
    officer_name  = company.get("officer_name") or company.get("email") or "Recruiter"
    officer_email = company.get("email") or ""

    if body.email_type not in ("shortlist", "interview_invite", "rejection", "offer"):
        raise HTTPException(status_code=400, detail="Invalid email_type.")

    candidates = _get_candidates_for_job(body.job_id, company_id)
    cand       = next((c for c in candidates if c["user_id"] == body.candidate_id), None)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found for this job.")
    if not cand.get("email"):
        raise HTTPException(status_code=400, detail="Candidate has no email address on file.")

    # Duplicate guard
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT id FROM email_logs WHERE candidate_id=%s AND job_id=%s AND email_type=%s",
            (body.candidate_id, body.job_id, body.email_type),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"A '{body.email_type}' email was already sent to this candidate for this job.",
            )
    finally:
        cur.close()
        conn.close()

    job       = _resolve_job(body.job_id, company_id)
    job_title = job.get("title", "the role") if "error" not in job else "the role"
    cand_name = f"{cand['first_name']} {cand['last_name']}"
    subject, plain_body = _build_email_body(
        body.email_type, cand_name, job_title,
        company_name, officer_name, officer_email, "",
    )

    import html as _html_mod
    html_body = (
        "<!DOCTYPE html><html><body style='font-family:\"Segoe UI\",sans-serif;"
        "color:#e2e8f0;background:#0f0f1a;padding:32px;line-height:1.6'><p>"
        + _html_mod.escape(plain_body).replace("\n\n", "</p><p>").replace("\n", "<br>")
        + "</p></body></html>"
    )

    try:
        _send_email(cand["email"], subject, html_body)
    except Exception as exc:
        _log.error("Agentic send_email failed for candidate %d: %s", body.candidate_id, exc)
        raise HTTPException(status_code=500, detail=f"Email delivery failed: {exc}")

    # Map email type → application status
    _STATUS_MAP = {
        "shortlist":        "shortlisted",
        "interview_invite": "shortlisted",
        "rejection":        "rejected",
        "offer":            "shortlisted",
    }
    new_status = _STATUS_MAP.get(body.email_type)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO email_logs 
            (candidate_id, job_id, email_type, recruiter_id, sent_at) 
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (body.candidate_id, body.job_id, body.email_type, company_id, now),
        )
        # Keep application status in sync with the email action
        if new_status:
            cur.execute(
                "UPDATE job_applications SET status = %s WHERE user_id = %s AND job_id = %s",
                (new_status, body.candidate_id, body.job_id),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    _log.info(
        "Agentic email sent: type=%s candidate=%d job=%s recruiter=%d",
        body.email_type, body.candidate_id, body.job_id, company_id,
    )
    return {"status": "sent", "to": cand["email"], "email_type": body.email_type}
