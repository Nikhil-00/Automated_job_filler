"""
backend/config.py
─────────────────
Central configuration — all values come from the .env file at project root.
Fails hard at startup if any required variable is missing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ROOT = Path(__file__).parent.parent


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(
            f"[FATAL] Required environment variable '{key}' is not set. "
            "Add it to your .env file.",
            file=sys.stderr,
        )
        sys.exit(1)
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── Supabase / PostgreSQL ─────────────────────────────────────────────────────
SUPABASE_URL             = _require("SUPABASE_URL")
SUPABASE_DB_URL          = _require("SUPABASE_DB_URL")
SUPABASE_SERVICE_ROLE_KEY = _optional("SUPABASE_SERVICE_ROLE_KEY")

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET      = _require("JWT_SECRET")
ADMIN_PASSWORD  = _require("ADMIN_PASSWORD")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_DAYS = 7

# ── SMTP (Gmail) ──────────────────────────────────────────────────────────────
SMTP_HOST      = _optional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(_optional("SMTP_PORT", "465"))
EMAIL_ADDRESS  = _optional("EMAIL_ADDRESS", "auto.cv.filling@gmail.com")
EMAIL_PASSWORD = _require("EMAIL_PASSWORD")

# ── OpenAI (fallback for CV parsing) ──────────────────────────────────────────
OPENAI_API_KEY = _require("OPENAI_API_KEY")

# ── Groq (primary for CV Builder) ─────────────────────────────────────────────
GROQ_API_KEY = _optional("GROQ_API_KEY", "")

# ── CORS ──────────────────────────────────────────────────────────────────────
_cors_raw = _optional(
    "CORS_ORIGINS",
    "http://localhost:8080,http://localhost:8081,http://localhost:5173,"
    "http://localhost:3000,http://127.0.0.1:8080,http://127.0.0.1:8081,"
    "http://127.0.0.1:5173",
)
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

# ── Paths ─────────────────────────────────────────────────────────────────────
USER_DATA_DIR = PROJECT_ROOT / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)

VECTOR_DB_DIR = PROJECT_ROOT / "vector_db"
VECTOR_DB_DIR.mkdir(exist_ok=True)

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# ── Browser ───────────────────────────────────────────────────────────────────
BROWSER_HEADLESS = _optional("BROWSER_HEADLESS", "true").lower() == "true"
