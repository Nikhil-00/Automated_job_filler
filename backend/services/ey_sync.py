"""
backend/services/ey_sync.py
────────────────────────────
EY India jobs sync job.

Logic:
  1. Scrape all EY India job pages
  2. Upsert jobs that are new or updated
  3. Mark jobs not returned by the scrape as inactive (is_active=0)

Called by APScheduler every 24 hours and once at startup.
"""
from __future__ import annotations

from datetime import datetime

import time

from backend.database import get_connection
from backend.services.workday_fetcher import scrape_all_ey_jobs, fetch_job_description


def sync_ey_jobs() -> dict:
    """
    Full sync of EY India jobs.
    Returns summary dict: {scraped, inserted, deactivated, descriptions_fetched}.
    """
    print("[ey_sync] Starting EY India jobs sync…")

    # ── Scrape ────────────────────────────────────────────────────────────────
    try:
        scraped = scrape_all_ey_jobs(delay=0.15)
    except Exception as exc:
        print(f"[ey_sync] Scrape failed: {exc}")
        return {"error": str(exc)}

    print(f"[ey_sync] Scraped {len(scraped)} jobs from EY careers.")

    if not scraped:
        print("[ey_sync] No jobs returned — skipping DB update to avoid mass deactivation.")
        return {"scraped": 0, "inserted": 0, "deactivated": 0}

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    scraped_ids = [j["job_id"] for j in scraped]

    conn = get_connection()
    cur  = conn.cursor()

    # ── Step 1: Mark ALL existing active jobs as inactive ─────────────────────
    cur.execute("UPDATE ey_jobs SET is_active = 0 WHERE is_active = 1")

    # ── Step 2: Upsert scraped jobs (sets is_active=1) ────────────────────────
    inserted = 0
    for job in scraped:
        cur.execute(
            """
            INSERT INTO ey_jobs (job_id, title, location, url, first_seen, last_seen, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                title      = VALUES(title),
                location   = VALUES(location),
                url        = VALUES(url),
                last_seen  = VALUES(last_seen),
                is_active  = 1
            """,
            (job["job_id"], job["title"], job["location"], job["url"], now, now),
        )
        if cur.rowcount == 1:   # 1 = inserted
            inserted += 1

    # ── Step 3: Count how many stayed inactive (truly removed jobs) ───────────
    cur.execute("SELECT COUNT(*) FROM ey_jobs WHERE is_active = 0")
    (deactivated,) = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    # ── Step 4: Fetch descriptions for active jobs that don't have one ───────────
    conn2 = get_connection()
    cur2  = conn2.cursor(dictionary=True)
    cur2.execute("SELECT job_id, url FROM ey_jobs WHERE is_active = 1 AND description IS NULL")
    missing = cur2.fetchall()
    cur2.close()
    conn2.close()

    descriptions_fetched = 0
    print(f"[ey_sync] Fetching descriptions for {len(missing)} jobs…")
    for job in missing:
        desc = fetch_job_description(job["url"])
        if desc:
            conn3 = get_connection()
            cur3  = conn3.cursor()
            cur3.execute(
                "UPDATE ey_jobs SET description = %s WHERE job_id = %s",
                (desc, job["job_id"]),
            )
            conn3.commit()
            cur3.close()
            conn3.close()
            descriptions_fetched += 1
            print(f"[ey_sync] Cached description for job_id={job['job_id']}")
        time.sleep(0.5)   # polite delay between Playwright calls

    summary = {
        "scraped":              len(scraped),
        "inserted":             inserted,
        "deactivated":          deactivated,
        "descriptions_fetched": descriptions_fetched,
    }
    print(f"[ey_sync] Done — {summary}")
    return summary
