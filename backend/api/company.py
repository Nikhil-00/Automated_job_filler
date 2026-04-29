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

import uuid

import bcrypt
import jwt
import pdfplumber
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

_log = logging.getLogger(__name__)

# Discriminatory question guard — topics we must never answer
_PROHIBITED_RE = re.compile(
    r"\b(age|born|birth.?year|gender|sex(?:ual)?|religion|religious|"
    r"church|temple|mosque|married|marital|spouse|husband|wife|"
    r"pregnant|pregnancy|disabl\w*|caste|race|nationalit\w*|"
    r"ethnic\w*|divorce\w*)\b",
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
    application_id:  str | None = None     # applied_jobs.id — for LinkedIn-scraped JDs
    job_url:         str | None = None     # Big4 apply URL — joined against ey_jobs.url
    job_title:       str | None = None     # human-readable fallback when JD unavailable
    job_posting_id:  str | None = None     # job_postings.id — for World Wide portal jobs


class AiScoreRequest(BaseModel):
    application_id: str
    user_id:        int
    job_url:        str | None = None
    job_title:      str | None = None
    job_posting_id: str | None = None     # World Wide portal — look up JD from job_postings
    source:         str = "big4"          # "big4" | "portal" — determines which table to cache


class PortalAiScoreRequest(BaseModel):
    application_id: str                   # job_applications.id
    user_id:        int
    job_posting_id: str | None = None
    job_title:      str | None = None


_COMPANY_JWT_EXPIRE_HOURS = 24 * 7
_bearer = HTTPBearer()


def _create_company_jwt(
    company_id:   int,
    email:        str,
    company_name: str,
    company_key:  str,
    officer_name: str = "",
    company_type: str = "big4",
) -> str:
    payload = {
        "sub":          str(company_id),
        "email":        email,
        "company_name": company_name,
        "company_key":  company_key,
        "officer_name": officer_name,
        "company_type": company_type,
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


def _send_email(to: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.ehlo(); s.starttls()
        s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        s.send_message(msg)


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
    company_name:       str
    officer_name:       str
    email:              str
    phone:              str
    company_key:        str          # ey | deloitte | kpmg | pwc | other
    company_type:       str = "big4" # big4 | other
    custom_company_name: str = ""    # used when company_type == "other"


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/signup")
def company_signup(req: SignupRequest):
    """
    Accept company signup details, send OTP to their email.
    If email already exists but unverified — resend OTP.
    If already verified — reject with 409.
    """
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

        effective_name = req.custom_company_name.strip() if req.company_type == "other" and req.custom_company_name.strip() else req.company_name

        if existing and not existing["is_otp_verified"]:
            cur.execute(
                "UPDATE company_requests SET company_name=%s, officer_name=%s, phone=%s, company_key=%s, company_type=%s, otp_code=%s, otp_expires_at=%s WHERE id=%s",
                (effective_name, req.officer_name, req.phone, req.company_key, req.company_type, otp, expires, existing["id"]),
            )
        else:
            cur.execute(
                """INSERT INTO company_requests
                   (company_name, officer_name, email, phone, company_key, company_type, otp_code, otp_expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (effective_name, req.officer_name, req.email, req.phone, req.company_key, req.company_type, otp, expires),
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

        company_type = row.get("company_type", "big4") or "big4"

        if company_type == "other":
            # Auto-approve: generate credentials immediately
            plain_pw = secrets.token_urlsafe(12)
            hashed   = bcrypt.hashpw(plain_pw.encode(), bcrypt.gensalt()).decode()
            cur.execute(
                """UPDATE company_requests
                   SET is_otp_verified=1, otp_code=NULL,
                       assigned_email=%s, assigned_password=%s, status='approved'
                   WHERE id=%s""",
                (row["email"], hashed, row["id"]),
            )
            conn.commit()
            company    = dict(row)
            auto_creds = (row["email"], plain_pw)
        else:
            cur.execute(
                "UPDATE company_requests SET is_otp_verified=1, otp_code=NULL WHERE id=%s",
                (row["id"],),
            )
            conn.commit()
            company    = dict(row)
            auto_creds = None
    finally:
        cur.close()
        conn.close()

    if auto_creds:
        # Email credentials to the new company
        try:
            _send_email(
                auto_creds[0],
                "AutoApply AI — Your Company Portal Credentials",
                _credentials_email_html(
                    company["officer_name"],
                    company["company_name"],
                    auto_creds[0],
                    auto_creds[1],
                ),
            )
        except Exception:
            pass
        return {
            "message":      "Email verified. Your portal is ready — check your inbox for login credentials.",
            "company_type": "other",
            "auto_approved": True,
        }

    # Big4 — notify admin for manual credential assignment
    try:
        _send_email(
            EMAIL_ADDRESS,
            f"New Company Request: {company['company_name']}",
            _admin_notification_html(
                company["company_name"],
                company["officer_name"],
                company["email"],
                company["phone"],
            ),
        )
    except Exception:
        pass

    return {
        "message":      "Email verified successfully. Your request has been submitted for review.",
        "company_type": "big4",
        "auto_approved": False,
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

    company_type = company.get("company_type") or "big4"
    token = _create_company_jwt(
        company["id"],
        company["assigned_email"],
        company["company_name"],
        company.get("company_key") or "ey",
        company.get("officer_name") or "",
        company_type,
    )
    return {
        "token":        token,
        "company_name": company["company_name"],
        "officer_name": company["officer_name"],
        "email":        company["assigned_email"],
        "company_key":  company.get("company_key") or "ey",
        "company_type": company_type,
    }


# ── Applicants ────────────────────────────────────────────────────────────────

_APPLICANT_SORT_MAP = {
    "recent":     "aj.applied_at DESC",
    "score_high": "ISNULL(aj.ai_match_score), aj.ai_match_score DESC",
    "score_low":  "aj.ai_match_score IS NOT NULL, aj.ai_match_score ASC",
    "name":       "uc.first_name ASC, uc.last_name ASC",
}


@router.get("/applicants")
def get_applicants(
    search:     str = "",
    status:     str = "",        # "" | applied | shortlisted | rejected
    sort_by:    str = "recent",  # recent | score_high | score_low | name
    score_tier: str = "",        # "" | high | medium | low
    has_cv:     str = "",        # "" | yes | no
    company: dict = Depends(get_company_user),
):
    """Return all job seekers who applied to this company's jobs via the Big4 portal."""
    company_key = company.get("company_key", "ey")
    platform    = f"big4_{company_key}"

    conditions = ["aj.platform = %s"]
    params: list = [platform]

    if search:
        like = f"%{search}%"
        conditions.append(
            "(aj.title LIKE %s OR uc.first_name LIKE %s OR uc.last_name LIKE %s OR uc.email LIKE %s)"
        )
        params += [like, like, like, like]
    if status:
        conditions.append("aj.status = %s")
        params.append(status)
    if score_tier == "high":
        conditions.append("aj.ai_match_score >= 70")
    elif score_tier == "medium":
        conditions.append("aj.ai_match_score >= 45 AND aj.ai_match_score < 70")
    elif score_tier == "low":
        conditions.append("(aj.ai_match_score IS NULL OR aj.ai_match_score < 45)")
    if has_cv == "yes":
        conditions.append("uc.data_folder IS NOT NULL AND uc.data_folder != ''")
    elif has_cv == "no":
        conditions.append("(uc.data_folder IS NULL OR uc.data_folder = '')")

    order_clause = _APPLICANT_SORT_MAP.get(sort_by, "aj.applied_at DESC")
    where = " AND ".join(conditions)

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            f"""
            SELECT
                aj.id             AS application_id,
                aj.title          AS applied_for,
                aj.location,
                aj.applied_at,
                aj.url            AS job_url,
                aj.match_score,
                aj.ai_match_score,
                aj.ai_score_reason,
                aj.status,
                uc.id             AS user_id,
                uc.first_name,
                uc.last_name,
                uc.email,
                uc.phone,
                uc.data_folder
            FROM applied_jobs aj
            JOIN user_credentials uc ON aj.user_id = uc.id
            WHERE {where}
            ORDER BY {order_clause}
            """,
            params,
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        r["has_cv"] = bool(r.get("data_folder"))

    return {"applicants": rows, "total": len(rows), "company_key": company_key}


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


@router.patch("/applicants/{application_id}/status")
def update_applicant_status(
    application_id: str,
    body: ApplicantActionRequest,
    company: dict = Depends(get_company_user),
):
    """Shortlist (send email) or reject (delete) an applicant."""
    if body.action not in ("shortlist", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'shortlist' or 'reject'.")

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        # Fetch the application + candidate info
        cur.execute(
            """
            SELECT aj.id, aj.title, aj.status,
                   uc.first_name, uc.last_name, uc.email AS candidate_email
            FROM applied_jobs aj
            JOIN user_credentials uc ON aj.user_id = uc.id
            WHERE aj.id = %s
            """,
            (application_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")

        if body.action == "reject":
            cur.execute("DELETE FROM applied_jobs WHERE id = %s", (application_id,))
        else:
            cur.execute(
                "UPDATE applied_jobs SET status = 'shortlisted' WHERE id = %s",
                (application_id,),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    # Send congratulations email in background
    if body.action == "shortlist":
        officer_name  = company.get("officer_name", company.get("email", ""))
        officer_email = company.get("email", "")
        company_name  = company.get("company_name", "")
        candidate_name = f"{row['first_name']} {row['last_name']}"
        _send_email_background(
            row["candidate_email"],
            f"Your profile has been shortlisted by {company_name}",
            _shortlist_email_html(
                candidate_name,
                row["title"],
                company_name,
                officer_name,
                officer_email,
            ),
        )

    return {"message": "ok", "action": body.action}


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

    # ── 3. Load JD from ey_jobs (fetch + cache if missing) ───────────────────
    jd_text  = ""
    jd_title = body.job_title or ""

    if body.job_url:
        conn2 = get_connection()
        cur2  = conn2.cursor(dictionary=True)
        try:
            cur2.execute(
                "SELECT job_id, description FROM ey_jobs WHERE url = %s LIMIT 1",
                (body.job_url,),
            )
            ey_row = cur2.fetchone()
        finally:
            cur2.close()
            conn2.close()

        if ey_row:
            jd_text = ey_row.get("description") or ""
            if not jd_text:
                from backend.services.workday_fetcher import fetch_job_description
                jd_text = fetch_job_description(body.job_url)
                if jd_text and ey_row.get("job_id"):
                    conn3 = get_connection()
                    cur3  = conn3.cursor()
                    try:
                        cur3.execute(
                            "UPDATE ey_jobs SET description = %s WHERE job_id = %s",
                            (jd_text, ey_row["job_id"]),
                        )
                        conn3.commit()
                    finally:
                        cur3.close()
                        conn3.close()

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
    # Priority order:
    #   1. ey_jobs.description via job_url  (Big4 portal applicants)
    #   2. applied_jobs.description via application_id  (LinkedIn automation)
    #   3. Graceful fallback with job title only
    jd_title = body.job_title or ""
    jd_text  = ""

    if body.job_url:
        conn2 = get_connection()
        cur2  = conn2.cursor(dictionary=True)
        try:
            cur2.execute(
                "SELECT job_id, description FROM ey_jobs WHERE url = %s LIMIT 1",
                (body.job_url,),
            )
            ey_row = cur2.fetchone()
        finally:
            cur2.close()
            conn2.close()

        if ey_row:
            jd_text = ey_row.get("description") or ""

            # Cache miss — fetch live from EY and store so next call is instant
            if not jd_text:
                _log.info("JD cache miss for %s — fetching via Playwright", body.job_url)
                from backend.services.workday_fetcher import fetch_job_description
                jd_text = fetch_job_description(body.job_url)
                if jd_text and ey_row.get("job_id"):
                    conn3 = get_connection()
                    cur3  = conn3.cursor()
                    try:
                        cur3.execute(
                            "UPDATE ey_jobs SET description = %s WHERE job_id = %s",
                            (jd_text, ey_row["job_id"]),
                        )
                        conn3.commit()
                        _log.info("JD cached for job_id=%s", ey_row["job_id"])
                    finally:
                        cur3.close()
                        conn3.close()

    # Fallback: LinkedIn-automation-scraped description stored in applied_jobs
    if not jd_text and body.application_id:
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
                       (SELECT COUNT(*) FROM job_applications WHERE job_id = jp.id) AS applicant_count
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
                       (SELECT COUNT(*) FROM job_applications WHERE job_id = jp.id) AS applicant_count
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
            (1 if body.is_active else 0, job_id),
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
        "score_high": "ISNULL(ja.ai_match_score), ja.ai_match_score DESC",
        "score_low":  "ja.ai_match_score IS NOT NULL, ja.ai_match_score ASC",
        "name":       "uc.first_name ASC, uc.last_name ASC",
    }
    order_clause = _PORTAL_SORT.get(sort_by, "ja.applied_at DESC")
    where = " AND ".join(conditions)

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
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
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        r["has_cv"] = bool(r.get("data_folder"))

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
