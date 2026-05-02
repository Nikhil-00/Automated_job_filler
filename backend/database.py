"""
backend/database.py
────────────────────
PostgreSQL helpers with connection pooling (for Supabase).
Includes a wrapper to maintain compatibility with MySQL-style dictionary cursors.
"""
from __future__ import annotations

import logging
import threading
import psycopg2
from psycopg2 import pool, extras
from backend.config import SUPABASE_DB_URL

_log = logging.getLogger(__name__)

# ── Connection Wrapper ────────────────────────────────────────────────────────

class DictConnection:
    """
    A wrapper around psycopg2 connection to support .cursor(dictionary=True)
    syntax used in the original MySQL implementation.
    """
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        # Handle original MySQL dictionary=True parameter
        if kwargs.pop('dictionary', False):
            kwargs['cursor_factory'] = extras.RealDictCursor
        return self._conn.cursor(*args, **kwargs)

    def commit(self): return self._conn.commit()
    def rollback(self): return self._conn.rollback()
    def close(self):
        """Return the connection to the pool instead of closing it."""
        try:
            _get_pool().putconn(self._conn)
        except Exception as e:
            _log.error("Error returning connection to pool: %s", e)
    
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type: self._conn.rollback()
        else: self._conn.commit()
        self.close()

# ── Connection pool ───────────────────────────────────────────────────────────

_pool: pool.SimpleConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            _pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=SUPABASE_DB_URL
            )
    return _pool


def get_connection():
    """Return a pooled connection wrapped for dictionary support."""
    conn = _get_pool().getconn()
    return DictConnection(conn)


# ── One-time DB + table init ──────────────────────────────────────────────────

def init_db() -> None:
    """
    Create all required tables in PostgreSQL.
    Called once at server startup.
    """
    conn = psycopg2.connect(SUPABASE_DB_URL)
    cur = conn.cursor()

    # Enable pgvector extension
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # User credentials
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_credentials (
            id            SERIAL       PRIMARY KEY,
            first_name    VARCHAR(100) NOT NULL,
            last_name     VARCHAR(100) NOT NULL,
            email         VARCHAR(255) UNIQUE NOT NULL,
            phone         VARCHAR(30),
            password_hash VARCHAR(255) NOT NULL,
            role          VARCHAR(20)  DEFAULT 'user',
            is_verified   BOOLEAN      DEFAULT FALSE,
            data_folder   VARCHAR(600),
            created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # OTP codes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id            SERIAL       PRIMARY KEY,
            email      VARCHAR(255) NOT NULL,
            otp_code      VARCHAR(10)  NOT NULL,
            expires_at    TIMESTAMP    NOT NULL,
            used          BOOLEAN      DEFAULT FALSE,
            attempt_count SMALLINT     DEFAULT 0,
            created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_email_otp ON otp_codes (email);")

    # Applied jobs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id               VARCHAR(36)   PRIMARY KEY,
            user_id          INT           NOT NULL REFERENCES user_credentials(id) ON DELETE CASCADE,
            platform         VARCHAR(20)   NOT NULL,
            applied_at       TIMESTAMP     NOT NULL,
            session_role     VARCHAR(255)  DEFAULT '',
            session_location VARCHAR(255)  DEFAULT '',
            job_index        INT           DEFAULT 0,
            title            VARCHAR(500)  DEFAULT '',
            company          VARCHAR(500)  DEFAULT '',
            location         VARCHAR(300)  DEFAULT '',
            status           VARCHAR(30)   NOT NULL,
            reason           TEXT,
            description      TEXT,
            url              TEXT,
            match_score      INT           DEFAULT 0,
            ai_match_score   INT           DEFAULT NULL,
            ai_score_reason  TEXT          DEFAULT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_applied ON applied_jobs (user_id, applied_at);")

    # Company requests
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_requests (
            id                SERIAL        PRIMARY KEY,
            company_name      VARCHAR(255)  NOT NULL,
            officer_name      VARCHAR(255)  NOT NULL,
            email             VARCHAR(255)  NOT NULL,
            phone             VARCHAR(30)   NOT NULL,
            otp_code          VARCHAR(10),
            otp_expires_at    TIMESTAMP,
            is_otp_verified   BOOLEAN       DEFAULT FALSE,
            status            VARCHAR(20)   DEFAULT 'pending',
            assigned_email    VARCHAR(255)  DEFAULT NULL,
            assigned_password VARCHAR(255)  DEFAULT NULL,
            company_key       VARCHAR(20)   DEFAULT NULL,
            company_type      VARCHAR(10)   DEFAULT 'big4',
            custom_company_name VARCHAR(255) DEFAULT NULL,
            created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comp_email ON company_requests (email);")

    # Job postings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_postings (
            id              VARCHAR(36)  PRIMARY KEY,
            company_id      INT          NOT NULL REFERENCES company_requests(id) ON DELETE CASCADE,
            company_name    VARCHAR(255) NOT NULL,
            title           VARCHAR(500) NOT NULL,
            description     TEXT         NOT NULL,
            skills          TEXT         DEFAULT NULL,
            location        VARCHAR(300) DEFAULT '',
            work_mode       VARCHAR(20)  DEFAULT 'onsite',
            job_type        VARCHAR(30)  DEFAULT 'full-time',
            experience_min  INT          DEFAULT 0,
            experience_max  INT          DEFAULT 5,
            salary_min      BIGINT       DEFAULT NULL,
            salary_max      BIGINT       DEFAULT NULL,
            salary_currency VARCHAR(10)  DEFAULT 'INR',
            openings        INT          DEFAULT 1,
            is_active       BOOLEAN      DEFAULT TRUE,
            created_at      TIMESTAMP    NOT NULL,
            expires_at      TIMESTAMP    DEFAULT NULL,
            embedding       VECTOR(1536)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_active_created ON job_postings (is_active, created_at);")

    # Job applications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_applications (
            id              VARCHAR(36) PRIMARY KEY,
            job_id          VARCHAR(36) NOT NULL REFERENCES job_postings(id)      ON DELETE CASCADE,
            user_id         INT         NOT NULL REFERENCES user_credentials(id)  ON DELETE CASCADE,
            applied_at      TIMESTAMP   NOT NULL,
            status          VARCHAR(20) DEFAULT 'applied',
            ai_match_score  INT         DEFAULT NULL,
            ai_score_reason TEXT        DEFAULT NULL,
            UNIQUE (job_id, user_id)
        )
    """)

    # Email logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS email_logs (
            id           SERIAL       PRIMARY KEY,
            candidate_id INT          NOT NULL,
            job_id       VARCHAR(100) NOT NULL,
            email_type   VARCHAR(50)  NOT NULL,
            recruiter_id INT          NOT NULL,
            sent_at      TIMESTAMP    NOT NULL,
            UNIQUE (candidate_id, job_id, email_type)
        )
    """)

    # Candidate profile
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidate_profile (
            id                SERIAL       PRIMARY KEY,
            user_id           INT          NOT NULL UNIQUE REFERENCES user_credentials(id) ON DELETE CASCADE,
            years_experience  FLOAT        DEFAULT 0,
            expected_ctc      BIGINT       DEFAULT NULL,
            skills            TEXT         DEFAULT NULL,
            cv_summary        TEXT         DEFAULT NULL,
            current_job_title VARCHAR(255) DEFAULT NULL,
            is_active         BOOLEAN      DEFAULT TRUE,
            created_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            embedding         VECTOR(1536)
        )
    """)

    # Target roles
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidate_target_roles (
            id           SERIAL       PRIMARY KEY,
            candidate_id INT          NOT NULL REFERENCES user_credentials(id) ON DELETE CASCADE,
            job_title    VARCHAR(255) NOT NULL
        )
    """)

    # Job matches
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidate_job_matches (
            id               SERIAL      PRIMARY KEY,
            job_id           VARCHAR(36) NOT NULL REFERENCES job_postings(id)     ON DELETE CASCADE,
            user_id          INT         NOT NULL REFERENCES user_credentials(id) ON DELETE CASCADE,
            ai_score         INT         DEFAULT NULL,
            ai_reasoning     TEXT        DEFAULT NULL,
            shortlist_status VARCHAR(20) DEFAULT 'pending',
            matched_at       TIMESTAMP   NOT NULL,
            UNIQUE (job_id, user_id)
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    _log.info("[DB] Supabase tables verified / created.")
