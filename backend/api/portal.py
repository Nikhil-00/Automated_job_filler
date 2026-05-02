"""
backend/api/portal.py
──────────────────────
World Wide Jobs — job-seeker facing endpoints.

GET  /api/portal/jobs                — browse active postings (with filters + match score)
POST /api/portal/jobs/{job_id}/apply — apply to a posting
GET  /api/portal/applied             — my applications
GET  /api/portal/shortlisted         — jobs where candidate has been shortlisted
"""
from __future__ import annotations

import json as _json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.routes  import get_current_user
from backend.auth.service import get_user_by_id
from backend.config       import USER_DATA_DIR
from backend.database     import get_connection

router = APIRouter(prefix="/api/portal", tags=["portal"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_user_profile(user_id: int) -> dict:
    db_user = get_user_by_id(user_id)
    if db_user and db_user.get("data_folder"):
        p = USER_DATA_DIR / db_user["data_folder"] / "profile.json"
        if p.exists():
            try:
                return _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _keyword_match(job: dict, profile: dict) -> int:
    """Fast keyword overlap score (0-100) — no API cost."""
    import re
    STOP = {
        "with", "and", "the", "for", "that", "this", "from", "have",
        "will", "your", "able", "also", "about", "well", "must",
    }

    skills_val   = profile.get("skills", "")
    skills_str   = " ".join(skills_val) if isinstance(skills_val, list) else str(skills_val or "")
    profile_text = " ".join(filter(None, [
        str(profile.get("current_job_title", "") or ""),
        skills_str,
        str(profile.get("years_of_experience", "") or ""),
    ])).lower()

    skills_raw = job.get("skills") or "[]"
    try:
        skills_list = _json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
    except Exception:
        skills_list = []

    job_text = f"{job['title']} {' '.join(skills_list)}".lower()

    profile_words = {w for w in re.findall(r"\b[a-z]{4,}\b", profile_text) if w not in STOP}
    job_words     = [w for w in re.findall(r"\b[a-z]{4,}\b", job_text)     if w not in STOP]

    if not job_words or not profile_words:
        return 50

    matches = sum(1 for w in job_words if w in profile_words)
    raw     = matches / len(job_words)
    return min(95, int(25 + raw * 70))


# ── Browse jobs ───────────────────────────────────────────────────────────────

_SORT_MAP = {
    "recent":       "jp.created_at DESC",
    "salary_high":  "ISNULL(jp.salary_max), jp.salary_max DESC",
    "salary_low":   "ISNULL(jp.salary_min), jp.salary_min ASC",
    # "match" is computed in Python after the query — fall back to recent for SQL
}


@router.get("/jobs")
def list_jobs(
    search:          str = "",
    location:        str = "",
    work_mode:       str = "",
    job_type:        str = "",
    salary_currency: str = "",
    company:         str = "",
    exp_min:         int = 0,
    exp_max:         int = 99,
    sal_min:         int = 0,
    sal_max:         int = 0,
    days_ago:        int = 0,          # 0=any, 1=today, 7=week, 30=month
    sort_by:         str = "recent",   # recent | salary_high | salary_low | match
    applied_filter:  str = "",          # "" | applied | not_applied
    limit:           int = 20,
    offset:          int = 0,
    user: dict = Depends(get_current_user),
):
    """Return active job postings with keyword match scores."""
    user_id = int(user["sub"])
    profile = _load_user_profile(user_id)

    conditions = ["jp.is_active = 1", "jp.experience_min <= %s", "jp.experience_max >= %s"]
    params: list = [exp_max, exp_min]

    if search:
        like = f"%{search}%"
        conditions.append(
            "(jp.title LIKE %s OR jp.description LIKE %s OR jp.skills LIKE %s OR jp.company_name LIKE %s)"
        )
        params += [like, like, like, like]
    if location:
        conditions.append("jp.location LIKE %s")
        params.append(f"%{location}%")
    if work_mode:
        conditions.append("jp.work_mode = %s")
        params.append(work_mode)
    if job_type:
        conditions.append("jp.job_type = %s")
        params.append(job_type)
    if salary_currency:
        conditions.append("jp.salary_currency = %s")
        params.append(salary_currency)
    if sal_min:
        conditions.append("(jp.salary_max IS NULL OR jp.salary_max >= %s)")
        params.append(sal_min)
    if sal_max:
        conditions.append("(jp.salary_min IS NULL OR jp.salary_min <= %s)")
        params.append(sal_max)
    if company:
        conditions.append("jp.company_name LIKE %s")
        params.append(f"%{company}%")
    if days_ago > 0:
        conditions.append("jp.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)")
        params.append(days_ago)
    if applied_filter == "applied":
        conditions.append(
            "EXISTS (SELECT 1 FROM job_applications WHERE job_id = jp.id AND user_id = %s)"
        )
        params.append(user_id)
    elif applied_filter == "not_applied":
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM job_applications WHERE job_id = jp.id AND user_id = %s)"
        )
        params.append(user_id)

    order_clause = _SORT_MAP.get(sort_by, "jp.created_at DESC")
    where = " AND ".join(conditions)

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            f"""
            SELECT jp.id, jp.company_name, jp.title, jp.description, jp.skills,
                   jp.location, jp.work_mode, jp.job_type,
                   jp.experience_min, jp.experience_max,
                   jp.salary_min, jp.salary_max, jp.salary_currency,
                   jp.openings, jp.created_at,
                   (SELECT id FROM job_applications
                    WHERE job_id = jp.id AND user_id = %s LIMIT 1) AS application_id
            FROM job_postings jp
            WHERE {where}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
            """,
            [user_id] + params + [limit, offset],
        )
        rows = cur.fetchall()

        cur.execute(
            f"SELECT COUNT(*) AS cnt FROM job_postings jp WHERE {where}",
            params,
        )
        total = cur.fetchone()["cnt"]
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
        r["match_score"] = _keyword_match(r, profile)
        r["applied"]     = r.pop("application_id") is not None

    # Client-requested sort by match: re-sort this page by computed score
    if sort_by == "match":
        rows.sort(key=lambda r: r["match_score"], reverse=True)

    return {"jobs": rows, "total": total, "limit": limit, "offset": offset}


# ── Apply ─────────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/apply")
def apply_to_job(job_id: str, user: dict = Depends(get_current_user)):
    """Apply to a World Wide job posting."""
    user_id = int(user["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT id, is_active FROM job_postings WHERE id = %s", (job_id,))
        job = cur.fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if not job["is_active"]:
            raise HTTPException(status_code=410, detail="This job is no longer accepting applications.")

        app_id     = str(uuid.uuid4())
        applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur.execute(
                "INSERT INTO job_applications (id, job_id, user_id, applied_at) VALUES (%s, %s, %s, %s)",
                (app_id, job_id, user_id, applied_at),
            )
            conn.commit()
        except Exception as exc:
            if getattr(exc, "errno", None) == 1062:  # duplicate
                raise HTTPException(status_code=409, detail="You have already applied to this job.")
            raise
    finally:
        cur.close()
        conn.close()

    return {"status": "applied", "application_id": app_id}


# ── My applications ───────────────────────────────────────────────────────────

@router.get("/applied")
def my_applications(user: dict = Depends(get_current_user)):
    """Return all portal job applications for the logged-in user."""
    user_id = int(user["sub"])

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT ja.id AS application_id, ja.applied_at, ja.status,
                   ja.ai_match_score, ja.ai_score_reason,
                   jp.id AS job_id, jp.title, jp.company_name, jp.location,
                   jp.work_mode, jp.job_type, jp.salary_min, jp.salary_max,
                   jp.salary_currency, jp.skills
            FROM job_applications ja
            JOIN job_postings jp ON jp.id = ja.job_id
            WHERE ja.user_id = %s
            ORDER BY ja.applied_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        try:
            r["skills"] = _json.loads(r["skills"]) if r.get("skills") else []
        except Exception:
            r["skills"] = []

    return rows


@router.get("/shortlisted")
def my_shortlisted_jobs(user: dict = Depends(get_current_user)):
    """
    Return all jobs where the job seeker has been shortlisted.
    Combines portal applications (job_applications) and automation
    applications (applied_jobs — linkedin/naukri/big4) in one list.
    """
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        # Portal jobs shortlisted by company
        cur.execute(
            """
            SELECT ja.id           AS application_id,
                   ja.applied_at,
                   ja.ai_match_score,
                   jp.id           AS job_id,
                   jp.title,
                   jp.company_name AS company,
                   jp.location,
                   jp.work_mode,
                   jp.job_type,
                   jp.salary_min,
                   jp.salary_max,
                   jp.salary_currency,
                   jp.skills,
                   'portal'        AS source,
                   NULL            AS platform,
                   NULL            AS job_url
            FROM   job_applications ja
            JOIN   job_postings     jp ON jp.id = ja.job_id
            WHERE  ja.user_id = %s AND ja.status = 'shortlisted'
            ORDER  BY ja.applied_at DESC
            """,
            (user_id,),
        )
        portal_rows = cur.fetchall()

        # Automation jobs shortlisted by company (linkedin / naukri / big4_*)
        cur.execute(
            """
            SELECT id          AS application_id,
                   applied_at,
                   ai_match_score,
                   NULL        AS job_id,
                   title,
                   company,
                   location,
                   NULL        AS work_mode,
                   NULL        AS job_type,
                   NULL        AS salary_min,
                   NULL        AS salary_max,
                   NULL        AS salary_currency,
                   NULL        AS skills,
                   'automation' AS source,
                   platform,
                   url         AS job_url
            FROM   applied_jobs
            WHERE  user_id = %s AND status = 'shortlisted'
            ORDER  BY applied_at DESC
            """,
            (user_id,),
        )
        auto_rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    rows = portal_rows + auto_rows
    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()
        try:
            r["skills"] = _json.loads(r["skills"]) if r.get("skills") else []
        except Exception:
            r["skills"] = []

    # Sort combined list newest first
    rows.sort(key=lambda x: x.get("applied_at") or "", reverse=True)
    return rows
