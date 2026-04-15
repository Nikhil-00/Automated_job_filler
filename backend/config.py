"""
backend/config.py
─────────────────
Central configuration — all values come from the .env file at project root.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent

# ── MySQL ─────────────────────────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_USER     = os.getenv("DB_USER",     "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "pandey")
DB_NAME     = os.getenv("DB_NAME",     "Auto_login_cv")

# ── JWT ───────────────────────────────────────────────────────────────────────
JWT_SECRET      = os.getenv("JWT_SECRET", "autoapply-secret-key-change-in-production")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_DAYS = 7

# ── SMTP (Gmail) ──────────────────────────────────────────────────────────────
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_ADDRESS  = os.getenv("EMAIL_ADDRESS",  "auto.cv.filling@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Paths ─────────────────────────────────────────────────────────────────────
USER_DATA_DIR = PROJECT_ROOT / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
