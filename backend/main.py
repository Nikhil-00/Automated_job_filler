"""
backend/main.py
────────────────
FastAPI application entry point.

Run from the project root with:
    uvicorn backend.main:app --reload --port 8000
or via the legacy shim:
    uvicorn server:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.auth.routes import router as auth_router
from backend.api.websocket import router as ws_router
from backend.api.cv import router as cv_router
from backend.api.automation import router as automation_router
from backend.api.jobs import router as jobs_router

app = FastAPI(title="AutoApply AI", version="2.0.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database init ─────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print(f"[WARN] DB init failed: {e}. Check MySQL is running and .env credentials.")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(cv_router)
app.include_router(automation_router)
app.include_router(jobs_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}
