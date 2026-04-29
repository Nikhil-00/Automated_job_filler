"""
backend/database.py
────────────────────
MySQL helpers with connection pooling.
Pool is initialised lazily after init_db() creates the database.
"""
from __future__ import annotations

import threading

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool

from backend.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_USER

# ── Connection pool ───────────────────────────────────────────────────────────

_pool: MySQLConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            _pool = MySQLConnectionPool(
                pool_name="autoapply",
                pool_size=10,
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                connect_timeout=10,
            )
    return _pool


def get_connection() -> mysql.connector.MySQLConnection:
    """Return a pooled connection to the database."""
    return _get_pool().get_connection()


# ── One-time DB + table init ──────────────────────────────────────────────────

def init_db() -> None:
    """
    Create the database (if it doesn't exist) and all required tables.
    Called once at server startup.  Uses a raw connection (not the pool)
    so it can connect before the target database exists.
    """
    bare = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD
    )
    cur = bare.cursor()
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    bare.commit()
    cur.close()
    bare.close()

    # Now use a direct (non-pooled) connection for DDL so the pool can be
    # initialised cleanly afterwards.
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_credentials (
            id            INT          AUTO_INCREMENT PRIMARY KEY,
            first_name    VARCHAR(100) NOT NULL,
            last_name     VARCHAR(100) NOT NULL,
            email         VARCHAR(255) UNIQUE NOT NULL,
            phone         VARCHAR(30),
            password_hash VARCHAR(255) NOT NULL,
            role          ENUM('user','admin','company') DEFAULT 'user',
            is_verified   BOOLEAN      DEFAULT FALSE,
            data_folder   VARCHAR(600),
            created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS otp_codes (
            id         INT         AUTO_INCREMENT PRIMARY KEY,
            email      VARCHAR(255) NOT NULL,
            otp_code   VARCHAR(10)  NOT NULL,
            expires_at DATETIME     NOT NULL,
            used       BOOLEAN      DEFAULT FALSE,
            attempt_count TINYINT   DEFAULT 0,
            created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_email_otp (email)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id               VARCHAR(36)   PRIMARY KEY,
            user_id          INT           NOT NULL,
            platform         VARCHAR(20)   NOT NULL,
            applied_at       DATETIME      NOT NULL,
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
            FOREIGN KEY (user_id) REFERENCES user_credentials(id) ON DELETE CASCADE,
            INDEX idx_user_applied (user_id, applied_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_requests (
            id                INT           AUTO_INCREMENT PRIMARY KEY,
            company_name      VARCHAR(255)  NOT NULL,
            officer_name      VARCHAR(255)  NOT NULL,
            email             VARCHAR(255)  NOT NULL,
            phone             VARCHAR(30)   NOT NULL,
            otp_code          VARCHAR(10),
            otp_expires_at    DATETIME,
            is_otp_verified   TINYINT(1)    DEFAULT 0,
            status            ENUM('pending','approved','rejected') DEFAULT 'pending',
            assigned_email    VARCHAR(255)  DEFAULT NULL,
            assigned_password VARCHAR(255)  DEFAULT NULL,
            company_key       VARCHAR(20)   DEFAULT NULL,
            created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_email (email)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Safe column additions — compatible with MySQL < 8.0.3 which lacks IF NOT EXISTS.
    # Error 1060 = "Duplicate column name" — already exists, safe to ignore.
    # Any other error is re-raised so real problems aren't silently swallowed.
    _migrations = [
        ("company_requests", "assigned_email",      "VARCHAR(255) DEFAULT NULL"),
        ("company_requests", "assigned_password",   "VARCHAR(255) DEFAULT NULL"),
        ("company_requests", "company_key",         "VARCHAR(20)  DEFAULT NULL"),
        ("company_requests", "company_type",        "VARCHAR(10)  DEFAULT 'big4'"),
        ("company_requests", "custom_company_name", "VARCHAR(255) DEFAULT NULL"),
        ("applied_jobs",     "match_score",         "INT          DEFAULT 0"),
        ("applied_jobs",     "ai_match_score",      "INT          DEFAULT NULL"),
        ("applied_jobs",     "ai_score_reason",     "TEXT         DEFAULT NULL"),
        ("otp_codes",        "attempt_count",       "TINYINT      DEFAULT 0"),
    ]
    for table, column, definition in _migrations:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except Exception as _e:
            if getattr(_e, "errno", None) != 1060:  # 1060 = duplicate column, already exists
                raise

    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_postings (
            id              VARCHAR(36)  PRIMARY KEY,
            company_id      INT          NOT NULL,
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
            is_active       TINYINT(1)   DEFAULT 1,
            created_at      DATETIME     NOT NULL,
            expires_at      DATETIME     DEFAULT NULL,
            FOREIGN KEY (company_id) REFERENCES company_requests(id) ON DELETE CASCADE,
            INDEX idx_active_created (is_active, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_applications (
            id              VARCHAR(36) PRIMARY KEY,
            job_id          VARCHAR(36) NOT NULL,
            user_id         INT         NOT NULL,
            applied_at      DATETIME    NOT NULL,
            status          VARCHAR(20) DEFAULT 'applied',
            ai_match_score  INT         DEFAULT NULL,
            ai_score_reason TEXT        DEFAULT NULL,
            FOREIGN KEY (job_id)  REFERENCES job_postings(id)      ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES user_credentials(id)  ON DELETE CASCADE,
            UNIQUE KEY uq_job_user (job_id, user_id),
            INDEX idx_job  (job_id),
            INDEX idx_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ey_jobs (
            job_id      VARCHAR(25)   PRIMARY KEY,
            title       VARCHAR(500)  NOT NULL,
            location    VARCHAR(300)  DEFAULT '',
            url         TEXT          NOT NULL,
            description TEXT          DEFAULT NULL,
            first_seen  DATETIME      NOT NULL,
            last_seen   DATETIME      NOT NULL,
            is_active   TINYINT(1)    DEFAULT 1,
            INDEX idx_active (is_active),
            FULLTEXT idx_ft_title (title)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("[DB] Tables verified / created.")
