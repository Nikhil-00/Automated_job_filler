"""
backend/database.py
────────────────────
MySQL connection helpers + one-time table initialisation.
Database  : Auto_login_cv
Tables    : user_credentials, otp_codes
"""
from __future__ import annotations

import mysql.connector
from mysql.connector import Error

from backend.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_USER


def get_connection() -> mysql.connector.MySQLConnection:
    """Return a fresh connection to the Auto_login_cv database."""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


def init_db() -> None:
    """
    Create the database (if it doesn't exist) and all required tables.
    Called once at server startup.
    """
    # ── Step 1: create the database ──────────────────────────────────────────
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

    # ── Step 2: create tables ─────────────────────────────────────────────────
    conn = get_connection()
    cur  = conn.cursor()

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
            FOREIGN KEY (user_id) REFERENCES user_credentials(id) ON DELETE CASCADE,
            INDEX idx_user_applied (user_id, applied_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("[DB] Tables verified / created.")
