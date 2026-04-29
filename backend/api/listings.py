"""
backend/api/listings.py
────────────────────────
Big-4 / company job-listing endpoints.

GET  /api/listings/{company}                — jobs from DB (EY India)
GET  /api/listings/ey/{job_id}/description  — lazy-fetched description
POST /api/listings/apply                    — record manual apply in applied_jobs
POST /api/listings/sync                     — admin: trigger immediate sync
"""
from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.routes  import get_current_user
from backend.auth.service import get_user_by_id
from backend.api.jobs     import append_job_entry
from backend.config       import PROJECT_ROOT, USER_DATA_DIR
from backend.database     import get_connection
from backend.services.workday_fetcher import (
    compute_match_score,
    fetch_job_description,
    get_jobs_from_db,
)

router = APIRouter(tags=["listings"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_profile(user_id: int) -> dict:
    db_user = get_user_by_id(user_id)
    if db_user.get("data_folder"):
        p = USER_DATA_DIR / db_user["data_folder"] / "profile.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    p = PROJECT_ROOT / "profile.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


# ── Job listings ──────────────────────────────────────────────────────────────

@router.get("/api/listings/{company}")
async def get_listings(
    company: str,
    search:  str = "",
    limit:   int = 20,
    offset:  int = 0,
    user:    dict = Depends(get_current_user),
):
    """Fetch EY India jobs from DB and attach a keyword match score."""
    if company != "ey":
        raise HTTPException(status_code=404, detail=f"{company} listings are coming soon.")

    try:
        result = get_jobs_from_db(search=search, limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DB error: {exc}")

    profile = _load_profile(int(user["sub"]))
    for job in result["jobs"]:
        job["match_score"] = compute_match_score(
            job["title"],
            job.get("bullet_fields", []),
            profile,
        )

    return result


# ── Description (lazy fetch + cache) ─────────────────────────────────────────

@router.get("/api/listings/ey/{job_id}/description")
async def get_description(
    job_id: str,
    user:   dict = Depends(get_current_user),
):
    """
    Return the description for an EY job.
    If not cached in DB, fetches the detail page, stores, and returns it.
    """
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT url, description FROM ey_jobs WHERE job_id = %s",
        (job_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")

    # Already cached
    if row["description"] is not None:
        return {"description": row["description"]}

    # Fetch live via Playwright (sync) — run in thread to avoid blocking event loop
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        desc = await loop.run_in_executor(pool, fetch_job_description, row["url"])

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE ey_jobs SET description = %s WHERE job_id = %s",
        (desc, job_id),
    )
    conn.commit()
    cur.close()
    conn.close()

    return {"description": desc}


# ── Manual apply record ───────────────────────────────────────────────────────

class _ApplyRequest(BaseModel):
    job_id:      str
    title:       str
    company:     str
    company_key: str
    location:    str
    apply_url:   str
    match_score: int = 0


@router.post("/api/listings/apply")
async def apply_job(
    req:  _ApplyRequest,
    user: dict = Depends(get_current_user),
):
    """Record a Big-4 job as applied in the applied_jobs history table."""
    user_id = int(user["sub"])
    entry = {
        "id":               str(uuid.uuid4()),
        "platform":         f"big4_{req.company_key}",
        "applied_at":       datetime.now(timezone.utc).isoformat(),
        "title":            req.title,
        "company":          req.company,
        "location":         req.location,
        "status":           "applied",
        "url":              req.apply_url,
        "reason":           f"Applied via Big-4 listings (match: {req.match_score}%)",
        "session_role":     req.title,
        "session_location": req.location,
        "index":            0,
        "match_score":      req.match_score,
    }
    append_job_entry(user_id, entry)
    return {"status": "applied"}


# ── Admin: manual sync trigger ────────────────────────────────────────────────

@router.post("/api/listings/sync")
async def trigger_sync(user: dict = Depends(get_current_user)):
    """Trigger an immediate EY sync (runs in foreground — may be slow)."""
    from backend.services.ey_sync import sync_ey_jobs
    result = sync_ey_jobs()
    return result
