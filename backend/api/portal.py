"""
backend/api/portal.py
──────────────────────
World Wide Jobs — job-seeker facing endpoints.

GET  /api/portal/jobs                — browse active postings (with filters + match score)
POST /api/portal/jobs/{job_id}/apply — apply to a posting
GET  /api/portal/shortlisted         — jobs where candidate has been shortlisted
GET  /api/portal/all-applications    — all portal applications + passive matches
"""
from __future__ import annotations

import json as _json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.routes  import get_current_user
from backend.auth.service import get_user_by_id
from backend.config       import USER_DATA_DIR
from backend.database     import get_connection

router = APIRouter(prefix="/api/portal", tags=["portal"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_user_profile(user_id: int) -> tuple[dict, dict]:
    """Return (profile_json, cv_data_json) for the user. Either can be {} if missing."""
    db_user = get_user_by_id(user_id)
    profile: dict = {}
    cv:      dict = {}
    if db_user and db_user.get("data_folder"):
        base = USER_DATA_DIR / db_user["data_folder"]
        p = base / "profile.json"
        if p.exists():
            try:
                profile = _json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        c = base / "cv_data.json"
        if c.exists():
            try:
                cv = _json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                pass
    return profile, cv


def _total_exp_years(work_experience: list) -> float:
    """Calculate total years of experience from work history."""
    import re as _re
    total = 0.0
    now   = datetime.now()
    for w in work_experience:
        try:
            start_raw = str(w.get("start_date") or "")
            end_raw   = str(w.get("end_date")   or "")
            start_y   = int(_re.search(r"\d{4}", start_raw).group()) if _re.search(r"\d{4}", start_raw) else None
            if not start_y:
                continue
            if w.get("currently_working") or not end_raw or end_raw.lower() in ("present", "current", "now"):
                end_y = now.year
            else:
                end_y = int(_re.search(r"\d{4}", end_raw).group()) if _re.search(r"\d{4}", end_raw) else now.year
            total += max(0, end_y - start_y)
        except Exception:
            continue
    return total


def _score_for_portal(job: dict, profile: dict, cv: dict) -> int:
    """
    Score a candidate against a job using both profile.json and cv_data.json.

    Signals:
      Skills match   — 40 pts
      Experience     — 20 pts
      Role relevance — 20 pts
      Location       — 10 pts
      Education/cert — 10 pts
    Returns 0–95. Returns 0 when candidate has no data at all.
    """
    import re

    # ── Guard: no data → 0, not a fake number ────────────────────────────────
    has_any_data = any([
        profile.get("current_job_title"),
        profile.get("skills"),
        profile.get("years_of_experience"),
        cv.get("skills"),
        cv.get("work_experience"),
        cv.get("education"),
        cv.get("summary"),
    ])
    if not has_any_data:
        return 0

    score = 0

    # ── Skills (40 pts) ──────────────────────────────────────────────────────
    # Collect from both sources
    raw_profile_skills = profile.get("skills") or []
    if isinstance(raw_profile_skills, str):
        raw_profile_skills = [s.strip() for s in raw_profile_skills.split(",") if s.strip()]
    cv_tech = (cv.get("skills") or {}).get("technical") or []
    cv_soft = (cv.get("skills") or {}).get("soft") or []
    all_skills = list({s.lower().strip() for s in raw_profile_skills + cv_tech + cv_soft if s})

    skills_raw = job.get("skills") or "[]"
    try:
        job_skills = [s.lower().strip() for s in (_json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw)]
    except Exception:
        job_skills = []

    if job_skills and all_skills:
        matched = sum(1 for js in job_skills if any(js in cs or cs in js for cs in all_skills))
        score  += int((matched / len(job_skills)) * 40)
    elif all_skills:
        # No structured skills on the job — fall back to keyword overlap against description
        job_desc = (job.get("description") or "").lower()
        kw_hits  = sum(1 for s in all_skills if len(s) > 3 and s in job_desc)
        score   += min(20, kw_hits * 4)

    # ── Experience (20 pts) ──────────────────────────────────────────────────
    exp_years = float(profile.get("years_of_experience") or 0)
    if not exp_years and cv.get("work_experience"):
        exp_years = _total_exp_years(cv.get("work_experience") or [])

    exp_min = int(job.get("experience_min") or 0)
    exp_max = int(job.get("experience_max") or 99)

    if exp_min <= exp_years <= exp_max:
        score += 20
    elif exp_years > exp_max:
        score += 10  # overqualified — partial credit
    elif exp_years > 0:
        score += 5   # has some experience but below requirement

    # ── Role relevance (20 pts) ──────────────────────────────────────────────
    STOP = {"with", "that", "this", "have", "from", "they", "will", "your", "been", "also", "into"}
    job_title   = (job.get("title") or "").lower()
    title_words = [w for w in re.findall(r"\b[a-z]{4,}\b", job_title) if w not in STOP]

    candidate_role_text = " ".join(filter(None, [
        (profile.get("current_job_title") or "").lower(),
        (cv.get("summary") or "").lower(),
        " ".join(
            f"{w.get('title', '')} {w.get('company', '')}".lower()
            for w in (cv.get("work_experience") or [])[:3]
        ),
    ]))

    if title_words and candidate_role_text:
        hits   = sum(1 for w in title_words if w in candidate_role_text)
        score += int((hits / len(title_words)) * 20)

    # ── Location (10 pts) ────────────────────────────────────────────────────
    if job.get("work_mode") == "remote":
        score += 10  # remote job — location irrelevant
    else:
        job_loc  = (job.get("location") or "").lower().strip()
        cand_loc = (
            profile.get("location")
            or (cv.get("contact") or {}).get("location")
            or ""
        ).lower().strip()
        if job_loc and cand_loc and (job_loc in cand_loc or cand_loc in job_loc):
            score += 10

    # ── Education / Certifications (10 pts) ──────────────────────────────────
    if cv.get("education") or profile.get("education"):
        score += 5
    if cv.get("certifications"):
        score += 5

    return max(0, min(95, score))


# ── Browse jobs ───────────────────────────────────────────────────────────────

_SORT_MAP = {
    "recent":       "jp.created_at DESC",
    "salary_high":  "jp.salary_max IS NULL, jp.salary_max DESC",
    "salary_low":   "jp.salary_min IS NULL, jp.salary_min ASC",
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
    days_ago:        int = 0,
    sort_by:         str = "recent",
    applied_filter:  str = "",
    limit:           int = 20,
    offset:          int = 0,
    user: dict = Depends(get_current_user),
):
    """Return active job postings with keyword match scores."""
    user_id         = int(user["sub"])
    profile, cv     = _load_user_profile(user_id)

    conditions = ["jp.is_active = TRUE", "jp.experience_min <= %s", "jp.experience_max >= %s"]
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
        conditions.append("jp.created_at >= NOW() - (%s * INTERVAL '1 day')")
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

    clean = []
    for r in rows:
        row = dict(r)
        if isinstance(row.get("created_at"), datetime):
            row["created_at"] = row["created_at"].isoformat()
        try:
            row["skills"] = _json.loads(row["skills"]) if row.get("skills") else []
        except Exception:
            row["skills"] = []
        row["match_score"] = _score_for_portal(row, profile, cv)
        row["applied"]     = row.pop("application_id") is not None
        clean.append(row)

    if sort_by == "match":
        clean.sort(key=lambda r: r["match_score"], reverse=True)

    return {"jobs": clean, "total": total, "limit": limit, "offset": offset}


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
            # Remove any passive match now that it's a manual application
            cur.execute(
                "DELETE FROM candidate_job_matches WHERE job_id = %s AND user_id = %s",
                (job_id, user_id)
            )
            conn.commit()
        except Exception as exc:
            pgcode = getattr(exc, "pgcode", None)
            if pgcode == "23505":
                raise HTTPException(status_code=409, detail="You have already applied to this job.")
            raise
    finally:
        cur.close()
        conn.close()

    return {"status": "applied", "application_id": app_id}


# ── Shortlisted ───────────────────────────────────────────────────────────────

@router.get("/shortlisted")
def my_shortlisted_jobs(user: dict = Depends(get_current_user)):
    """Return all portal jobs where the candidate has been shortlisted."""
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
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
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    result = []
    for r in rows:
        row = dict(r)
        if isinstance(row.get("applied_at"), datetime):
            row["applied_at"] = row["applied_at"].isoformat()
        try:
            row["skills"] = _json.loads(row["skills"]) if row.get("skills") else []
        except Exception:
            row["skills"] = []
        result.append(row)

    return result


# ── All applications ──────────────────────────────────────────────────────────

@router.get("/all-applications")
def all_applications(user: dict = Depends(get_current_user)):
    """
    Unified list of all applications for the logged-in user.
    Merges:
      1. Portal applications (job_applications table)
      2. Passive AI matches (candidate_job_matches table — "Your Job on Us")
    """
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        # 1. Portal applications
        cur.execute(
            """
            SELECT ja.id           AS id,
                   ja.applied_at,
                   ja.status,
                   ja.ai_match_score,
                   ja.ai_score_reason,
                   jp.title,
                   jp.company_name AS company,
                   jp.location,
                   jp.work_mode,
                   jp.job_type,
                   'Portal'        AS source,
                   NULL            AS platform,
                   NULL            AS url
            FROM   job_applications ja
            JOIN   job_postings     jp ON jp.id = ja.job_id
            WHERE  ja.user_id = %s
            ORDER  BY ja.applied_at DESC
            """,
            (user_id,),
        )
        portal_rows = cur.fetchall()

        # 2. Passive AI matches ("Your Job on Us")
        cur.execute(
            """
            SELECT cjm.id           AS id,
                   cjm.matched_at   AS applied_at,
                   cjm.shortlist_status AS status,
                   cjm.ai_score     AS ai_match_score,
                   cjm.ai_reasoning AS ai_score_reason,
                   jp.title,
                   jp.company_name  AS company,
                   jp.location,
                   jp.work_mode,
                   jp.job_type,
                   'Match'          AS source,
                   'Your Job on Us' AS platform,
                   NULL             AS url
            FROM   candidate_job_matches cjm
            JOIN   job_postings          jp ON jp.id = cjm.job_id
            WHERE  cjm.user_id = %s
            ORDER  BY cjm.matched_at DESC
            """,
            (user_id,),
        )
        match_rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    rows = [dict(r) for r in portal_rows] + [dict(r) for r in match_rows]
    for r in rows:
        if isinstance(r.get("applied_at"), datetime):
            r["applied_at"] = r["applied_at"].isoformat()

    rows.sort(key=lambda x: x.get("applied_at") or "", reverse=True)
    return rows
