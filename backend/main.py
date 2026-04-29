"""
backend/main.py
────────────────
FastAPI application entry point.

Run from the project root with:
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import CORS_ORIGINS
from backend.database import get_connection, init_db
from backend.auth.routes import router as auth_router
from backend.api.websocket import router as ws_router
from backend.api.cv import router as cv_router
from backend.api.automation import router as automation_router
from backend.api.jobs import router as jobs_router
from backend.api.listings import router as listings_router
from backend.api.company     import router as company_router
from backend.api.admin       import router as admin_router
from backend.api.cv_builder  import router as cv_builder_router
from backend.api.portal      import router as portal_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger(__name__)

app = FastAPI(title="AutoApply AI", version="2.0.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Scheduler ─────────────────────────────────────────────────────────────────
_scheduler = BackgroundScheduler(daemon=True)


def _run_ey_sync() -> None:
    try:
        from backend.services.ey_sync import sync_ey_jobs
        sync_ey_jobs()
    except Exception as exc:
        _log.error("EY sync error: %s", exc)


def _run_session_cleanup() -> None:
    try:
        from backend.shared_state import cleanup_stale_sessions
        removed = cleanup_stale_sessions()
        if removed:
            _log.info("Session cleanup: removed %d stale sessions.", removed)
    except Exception as exc:
        _log.error("Session cleanup error: %s", exc)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup() -> None:
    try:
        init_db()
    except Exception as e:
        _log.warning("DB init failed: %s. Check MySQL is running and .env credentials.", e)

    _scheduler.add_job(_run_ey_sync,          "cron",     hour=2,  minute=0,  id="ey_daily_sync")
    _scheduler.add_job(_run_session_cleanup,   "interval", hours=1,            id="session_cleanup")
    _scheduler.start()
    _log.info("Scheduler started (EY sync @ 02:00 UTC, session cleanup hourly).")

    def _initial_sync() -> None:
        try:
            conn = get_connection()
            cur  = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ey_jobs WHERE is_active=1")
            (count,) = cur.fetchone()
            cur.close()
            conn.close()
            if count == 0:
                _log.info("DB empty — running initial EY sync…")
                _run_ey_sync()
            else:
                _log.info("EY jobs DB has %d active jobs — skipping initial sync.", count)
        except Exception as exc:
            _log.error("Initial sync check failed: %s", exc)

    threading.Thread(target=_initial_sync, daemon=True).start()


@app.on_event("shutdown")
def shutdown() -> None:
    _scheduler.shutdown(wait=False)


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(cv_router)
app.include_router(automation_router)
app.include_router(jobs_router)
app.include_router(listings_router)
app.include_router(company_router)
app.include_router(admin_router)
app.include_router(cv_builder_router)
app.include_router(portal_router)


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
