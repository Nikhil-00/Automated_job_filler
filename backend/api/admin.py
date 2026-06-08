"""
backend/api/admin.py
─────────────────────
Hidden admin portal API. Credentials are hardcoded — not exposed in .env.
Route prefix: /api/admin
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.config import JWT_ALGORITHM, JWT_SECRET
from backend.database import get_connection

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ── Hardcoded credentials ─────────────────────────────────────────────────────

_ADMIN_EMAIL    = "nikhilishere@gmail.com"
_ADMIN_PASSWORD = "123456"
_TOKEN_HOURS    = 12

# ── JWT helpers ───────────────────────────────────────────────────────────────

def _create_admin_token() -> str:
    payload = {
        "role": "admin",
        "exp":  datetime.now(timezone.utc) + timedelta(hours=_TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


_bearer = HTTPBearer()

def _get_admin_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token.")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not an admin token.")
    return payload


# ── Request models ────────────────────────────────────────────────────────────

class AdminLoginRequest(BaseModel):
    email:    str
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
def admin_login(req: AdminLoginRequest):
    if req.email != _ADMIN_EMAIL or req.password != _ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return {"token": _create_admin_token()}


@router.get("/recruiters")
def get_recruiters(_: dict = Depends(_get_admin_user)):
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT
                c.id,
                c.company_name,
                c.officer_name,
                c.email,
                c.company_type,
                c.status,
                c.created_at,
                COUNT(j.id) AS total_jobs,
                SUM(CASE WHEN j.is_active THEN 1 ELSE 0 END) AS active_jobs
            FROM company_requests c
            LEFT JOIN job_postings j ON j.company_id = c.id
            WHERE c.is_otp_verified = TRUE
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """)
        companies = cur.fetchall()

        cur.execute("""
            SELECT company_id, id AS job_id, title, is_active, openings, created_at
            FROM job_postings
            ORDER BY created_at DESC
        """)
        all_jobs = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    jobs_by_company: dict[int, list] = {}
    for j in all_jobs:
        cid = j["company_id"]
        if cid not in jobs_by_company:
            jobs_by_company[cid] = []
        jobs_by_company[cid].append({
            "job_id":    j["job_id"],
            "title":     j["title"],
            "is_active": j["is_active"],
            "openings":  j["openings"],
            "created_at": j["created_at"].isoformat() if j.get("created_at") else None,
        })

    result = []
    for c in companies:
        result.append({
            "id":           c["id"],
            "company_name": c["company_name"],
            "officer_name": c["officer_name"],
            "email":        c["email"],
            "company_type": c["company_type"],
            "status":       c["status"],
            "created_at":   c["created_at"].isoformat() if c.get("created_at") else None,
            "total_jobs":   int(c["total_jobs"] or 0),
            "active_jobs":  int(c["active_jobs"] or 0),
            "jobs":         jobs_by_company.get(c["id"], []),
        })

    return {
        "total_recruiters": len(result),
        "recruiters":       result,
    }


@router.get("/jobseekers")
def get_jobseekers(_: dict = Depends(_get_admin_user)):
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) AS total FROM user_credentials WHERE role = 'user'")
        total = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) AS autopilot_on
            FROM candidate_profile
            WHERE is_active = TRUE
        """)
        autopilot_on = cur.fetchone()["autopilot_on"]

        cur.execute("""
            SELECT COUNT(*) AS with_profile
            FROM candidate_profile
        """)
        with_profile = cur.fetchone()["with_profile"]

        cur.execute("""
            SELECT
                u.id,
                u.first_name,
                u.last_name,
                u.email,
                u.created_at,
                CASE WHEN cp.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_profile,
                COALESCE(cp.is_active, FALSE) AS autopilot_on,
                cp.current_job_title,
                cp.years_experience
            FROM user_credentials u
            LEFT JOIN candidate_profile cp ON cp.user_id = u.id
            WHERE u.role = 'user'
            ORDER BY u.created_at DESC
        """)
        candidates = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    candidate_list = []
    for c in candidates:
        candidate_list.append({
            "id":               c["id"],
            "name":             f"{c['first_name']} {c['last_name']}".strip(),
            "email":            c["email"],
            "joined":           c["created_at"].isoformat() if c.get("created_at") else None,
            "has_profile":      c["has_profile"],
            "autopilot_on":     c["autopilot_on"],
            "current_job_title": c.get("current_job_title") or "—",
            "years_experience": c.get("years_experience"),
        })

    return {
        "total_candidates": total,
        "with_profile":     with_profile,
        "autopilot_on":     autopilot_on,
        "autopilot_off":    with_profile - autopilot_on,
        "candidates":       candidate_list,
    }
