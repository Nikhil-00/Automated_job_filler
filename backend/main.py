"""
backend/main.py
────────────────
FastAPI application entry point.

Run from the project root with:
    python -m uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import get_connection, init_db
from backend.auth.routes import router as auth_router
from backend.api.cv import router as cv_router
from backend.api.company import router as company_router
from backend.api.cv_builder import router as cv_builder_router
from backend.api.portal import router as portal_router
from backend.api.jobseeker_matching import router as jobseeker_matching_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger(__name__)

app = FastAPI(title="NewAgeNaukri", version="2.0.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
import os as _os

_raw_origins = _os.getenv("ALLOWED_ORIGINS", "*")
_origins = (
    ["*"]
    if _raw_origins.strip() == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup() -> None:
    try:
        init_db()
    except Exception as e:
        _log.warning("DB init failed: %s. Check Supabase connection and .env credentials.", e)


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(cv_router)
app.include_router(company_router)
app.include_router(cv_builder_router)
app.include_router(portal_router)
app.include_router(jobseeker_matching_router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    """Liveness + readiness probe — checks DB connectivity."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    if not db_ok:
        from fastapi import Response
        return Response(
            content='{"status":"degraded","db":false}',
            status_code=503,
            media_type="application/json",
        )

    return {"status": "ok", "version": "2.0.0", "db": True}
