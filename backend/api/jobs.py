"""
backend/api/jobs.py
────────────────────
Applied-jobs history endpoints (MySQL-backed).

GET    /api/jobs/applied        — all applications for the logged-in user (JOIN with user_credentials)
DELETE /api/jobs/applied/{id}   — delete a single entry by UUID
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.routes import get_current_user
from backend.database import get_connection

router = APIRouter(tags=["jobs"])


# ── Internal helper (called by automation worker) ─────────────────────────────

def append_job_entry(user_id: int, entry: dict) -> None:
    """
    Insert one CompanyEntry row into applied_jobs.
    Called from _PersistingLogger.company() in automation.py.
    """
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO applied_jobs
                (id, user_id, platform, applied_at, session_role, session_location,
                 job_index, title, company, location, status, reason, description, url, match_score)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                entry.get("id",               str(uuid.uuid4())),
                user_id,
                entry.get("platform",         ""),
                entry.get("applied_at",       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
                entry.get("session_role",     ""),
                entry.get("session_location", ""),
                entry.get("index",            0),
                entry.get("title",            ""),
                entry.get("company",          ""),
                entry.get("location",         ""),
                entry.get("status",           "skipped"),
                entry.get("reason",           ""),
                entry.get("description",      ""),
                entry.get("url",              ""),
                entry.get("match_score",      0),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"[jobs] Failed to save job entry: {exc}")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/api/jobs/applied")
def get_applied_jobs(user: dict = Depends(get_current_user)):
    """
    Return all applied jobs for the authenticated user, newest first.
    Uses a JOIN to include the user's name and email alongside each job.
    """
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT
                aj.id,
                aj.platform,
                aj.applied_at,
                aj.session_role,
                aj.session_location,
                aj.job_index  AS `index`,
                aj.title,
                aj.company,
                aj.location,
                aj.status,
                aj.reason,
                aj.description,
                aj.url,
                uc.first_name,
                uc.last_name,
                uc.email      AS user_email
            FROM  applied_jobs     aj
            JOIN  user_credentials uc ON uc.id = aj.user_id
            WHERE aj.user_id = %s
            ORDER BY aj.applied_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        # Convert datetime objects to ISO strings for JSON serialisation
        for row in rows:
            if isinstance(row.get("applied_at"), datetime):
                row["applied_at"] = row["applied_at"].isoformat()
        return rows
    finally:
        cur.close()
        conn.close()


@router.delete("/api/jobs/applied/{job_id}")
def delete_applied_job(job_id: str, user: dict = Depends(get_current_user)):
    """Delete a single job entry.  Only the owner can delete their own entries."""
    user_id = int(user["sub"])
    conn = get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM applied_jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Job entry not found.")
        return {"message": "Deleted."}
    finally:
        cur.close()
        conn.close()
