"""
backend/api/jobseeker_matching.py
───────────────────────────────────
"Your Job on Us" — passive candidate matching for job seekers.

POST   /api/jobseeker/activate   — activate + store profile for matching
GET    /api/jobseeker/activate   — get current activation status
DELETE /api/jobseeker/activate   — deactivate
"""
from __future__ import annotations

import json
import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.config import JWT_ALGORITHM, JWT_SECRET, USER_DATA_DIR
from backend.database import get_connection

_log    = logging.getLogger(__name__)
_bearer = HTTPBearer()

router = APIRouter(prefix="/api/jobseeker", tags=["jobseeker-matching"])


class ActivateRequest(BaseModel):
    target_roles:     list[str]
    expected_ctc_max: int | None = None


def _get_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") not in (None, "user"):
            raise ValueError
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


def _load_json(path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _generate_cv_summary(cv_data: dict, profile: dict) -> str:
    from backend.config import GROQ_API_KEY
    if not GROQ_API_KEY:
        title  = profile.get("current_job_title") or "Professional"
        exp    = profile.get("years_of_experience") or "0"
        skills = (cv_data.get("skills", {}).get("technical") or [])[:5]
        return f"{title} with {exp} years of experience. Skills: {', '.join(skills)}."

    try:
        work_exp  = cv_data.get("work_experience", [])
        skills    = cv_data.get("skills", {})
        education = cv_data.get("education", [])

        work_lines = "\n".join(
            f"- {w.get('title','?')} at {w.get('company','?')}" for w in work_exp[:3]
        )
        edu_lines  = "\n".join(
            f"- {e.get('degree','?')} from {e.get('institution','?')}" for e in education[:2]
        )
        tech_skills = ", ".join((skills.get("technical") or [])[:10])

        snippet = (
            f"Current title: {profile.get('current_job_title', 'N/A')}\n"
            f"Experience: {profile.get('years_of_experience', '0')} years\n"
            f"Skills: {tech_skills}\n"
            f"Work:\n{work_lines}\n"
            f"Education:\n{edu_lines}"
        )

        from groq import Groq as _Groq
        client = _Groq(api_key=GROQ_API_KEY)
        resp   = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Write a 2-3 sentence recruiter-style summary of this candidate. Be factual and concise."},
                {"role": "user",   "content": snippet},
            ],
            temperature=0.2,
            max_tokens=120,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        _log.warning("cv_summary generation failed: %s", exc)
        title = profile.get("current_job_title") or "Professional"
        exp   = profile.get("years_of_experience") or "0"
        return f"{title} with {exp} years of experience."


@router.post("/activate")
def activate(body: ActivateRequest, user: dict = Depends(_get_user)):
    user_id = int(user["sub"])

    roles = [r.strip() for r in body.target_roles if r.strip()][:3]
    if not roles:
        raise HTTPException(status_code=400, detail="Provide at least one job title.")

    # Load user data folder
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT data_folder FROM user_credentials WHERE id = %s", (user_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row or not row.get("data_folder"):
        raise HTTPException(status_code=400, detail="Please complete your CV and profile first.")

    folder  = USER_DATA_DIR / row["data_folder"]
    cv_data = _load_json(folder / "cv_data.json")
    profile = _load_json(folder / "profile.json")

    # Extract fields from profile.json
    try:
        years_exp = float(profile.get("years_of_experience") or 0)
    except (ValueError, TypeError):
        years_exp = 0.0

    # Use explicitly provided max CTC, else fall back to profile's expected_salary
    try:
        expected_ctc = body.expected_ctc_max or int(profile.get("expected_salary") or 0) or None
    except (ValueError, TypeError):
        expected_ctc = None

    skills_list = (cv_data.get("skills", {}).get("technical") or [])
    skills_json = json.dumps(skills_list)
    current_title = profile.get("current_job_title") or ""

    cv_summary = _generate_cv_summary(cv_data, profile)

    # Upsert candidate_profile
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO candidate_profile
                (user_id, years_experience, expected_ctc, skills, cv_summary, current_job_title, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (user_id) DO UPDATE SET
                years_experience  = EXCLUDED.years_experience,
                expected_ctc      = EXCLUDED.expected_ctc,
                skills            = EXCLUDED.skills,
                cv_summary        = EXCLUDED.cv_summary,
                current_job_title = EXCLUDED.current_job_title,
                is_active         = TRUE
            """,
            (user_id, years_exp, expected_ctc, skills_json, cv_summary, current_title),
        )
        cur.execute("DELETE FROM candidate_target_roles WHERE candidate_id = %s", (user_id,))
        for role in roles:
            cur.execute(
                "INSERT INTO candidate_target_roles (candidate_id, job_title) VALUES (%s, %s)",
                (user_id, role),
            )
        conn.commit()

        # ── Update Vector Store ───────────────────────────────────────────────
        try:
            from backend.utils.vector_store import upsert_candidate
            upsert_candidate(user_id, cv_summary, skills_list)
        except Exception as v_exc:
            _log.warning("Vector store update failed for user %s: %s", user_id, v_exc)

    finally:
        cur.close()
        conn.close()

    return {
        "message": "Activated. You'll be automatically matched to relevant jobs.",
        "roles":   roles,
    }


@router.get("/activate")
def get_activation_status(user: dict = Depends(_get_user)):
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT is_active, years_experience, expected_ctc, current_job_title FROM candidate_profile WHERE user_id = %s",
            (user_id,),
        )
        profile = cur.fetchone()
        roles: list[str] = []
        if profile:
            cur.execute(
                "SELECT job_title FROM candidate_target_roles WHERE candidate_id = %s",
                (user_id,),
            )
            roles = [r["job_title"] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    return {
        "is_active":     bool(profile and profile.get("is_active")),
        "target_roles":  roles,
        "expected_ctc":  profile.get("expected_ctc") if profile else None,
        "current_title": profile.get("current_job_title") if profile else None,
    }


@router.delete("/activate")
def deactivate(user: dict = Depends(_get_user)):
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute("UPDATE candidate_profile SET is_active = FALSE WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return {"message": "Deactivated. You will no longer be matched to jobs automatically."}
