"""
backend/services/workday_fetcher.py
─────────────────────────────────────
EY India job scraper — careers.ey.com/ey/search/?q=India

Proven approach: paginate via startrow=0,25,50,…
Parse <tr class="data-row"> rows.
Description is fetched lazily per job and cached in MySQL.
"""
from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL = "https://careers.ey.com/ey/search/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Referer":         "https://careers.ey.com/",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_PAGE_SIZE = 25

_STOP_WORDS = {
    "with", "that", "this", "have", "from", "they", "will", "your", "been",
    "more", "also", "into", "than", "then", "when", "where", "which", "some",
    "such", "each", "able", "well", "over", "just", "very",
}


# ── Job-ID helper ─────────────────────────────────────────────────────────────

def _job_id_from_url(url: str) -> str:
    """Extract the numeric job ID from an EY careers URL."""
    m = re.search(r"/(\d{8,13})/?$", url)
    return m.group(1) if m else url.rstrip("/").split("/")[-1]


# ── Single-page scraper ───────────────────────────────────────────────────────

def _scrape_page(start_row: int) -> tuple[BeautifulSoup, list[dict]]:
    params = {
        "createNewAlert": "false",
        "q":              "India",
        "startrow":       start_row,
    }
    for attempt in range(3):
        try:
            resp = requests.get(BASE_URL, params=params, headers=_HEADERS, timeout=45)
            resp.raise_for_status()
            break
        except requests.exceptions.Timeout:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
        except requests.exceptions.RequestException:
            raise
    soup = BeautifulSoup(resp.text, "html.parser")

    jobs: list[dict] = []
    for row in soup.find_all("tr", class_="data-row"):
        title_tag = row.find("a", class_="jobTitle-link")
        tds = row.find_all("td")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        href  = title_tag.get("href", "")
        url   = ("https://careers.ey.com" + href) if href.startswith("/") else href
        loc   = tds[1].get_text(strip=True) if len(tds) >= 2 else ""
        job_id = _job_id_from_url(url)

        jobs.append({
            "job_id":   job_id,
            "title":    title,
            "location": loc,
            "url":      url,
        })

    return soup, jobs


def _last_startrow(soup: BeautifulSoup) -> int | None:
    """Read the last page's startrow from pagination."""
    last = soup.find("a", class_="paginationItemLast")
    if last:
        href = last.get("href", "")
        try:
            return int(href.split("startrow=")[-1])
        except (ValueError, IndexError):
            pass
    return None


# ── Full scrape ───────────────────────────────────────────────────────────────

def scrape_all_ey_jobs(delay: float = 0.4) -> list[dict]:
    """
    Scrape every page of EY India jobs.
    Returns list of dicts: {job_id, title, location, url}.
    delay: seconds between requests (be polite).
    """
    all_jobs: list[dict] = []
    start_row = 0
    last_startrow: int | None = None

    while True:
        soup, jobs = _scrape_page(start_row)

        if start_row == 0:
            last_startrow = _last_startrow(soup)

        if not jobs:
            break

        all_jobs.extend(jobs)

        if last_startrow is not None and start_row >= last_startrow:
            break

        start_row += _PAGE_SIZE
        time.sleep(delay)

    # deduplicate by job_id (keep last seen)
    seen: dict[str, dict] = {}
    for j in all_jobs:
        seen[j["job_id"]] = j
    return list(seen.values())


# ── Description fetcher (lazy, called per job) ────────────────────────────────

def fetch_job_description(url: str) -> str:
    """
    Fetch the EY job detail page using Playwright and extract the description.
    The page is JavaScript-rendered, so a headless browser is required.
    Returns plain-text description (or empty string on failure).
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            el = page.query_selector("[class*='description']")
            desc = el.inner_text().strip() if el else ""
            browser.close()
            return desc
    except Exception:
        return ""


# ── DB API (serve from DB) ────────────────────────────────────────────────────

def get_jobs_from_db(
    search: str = "",
    limit:  int = 20,
    offset: int = 0,
) -> dict:
    """
    Read active EY jobs from MySQL with optional keyword filter.
    Returns {"jobs": [...], "total": int, "offset": int, "limit": int}.
    """
    from backend.database import get_connection

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)

    like = f"%{search}%" if search else "%"
    cur.execute(
        """
        SELECT job_id, title, location, url, description
        FROM   ey_jobs
        WHERE  is_active = 1
          AND  (title LIKE %s OR location LIKE %s)
        ORDER  BY last_seen DESC
        LIMIT  %s OFFSET %s
        """,
        (like, like, limit, offset),
    )
    rows = cur.fetchall()

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM ey_jobs WHERE is_active=1 AND (title LIKE %s OR location LIKE %s)",
        (like, like),
    )
    total = cur.fetchone()["cnt"]

    cur.close()
    conn.close()

    jobs = [
        {
            "id":            r["job_id"],
            "title":         r["title"],
            "location":      r["location"],
            "url":           r["url"],
            "apply_url":     r["url"],
            "posted_on":     "",
            "bullet_fields": [],
            "company":       "Ernst & Young",
            "company_key":   "ey",
            "has_description": r["description"] is not None,
        }
        for r in rows
    ]
    return {"jobs": jobs, "total": total, "offset": offset, "limit": limit}


# ── Match score (zero API cost) ───────────────────────────────────────────────

def compute_match_score(
    job_title:     str,
    bullet_fields: list,
    profile:       dict,
) -> int:
    """
    Keyword-overlap match score between a job and the user's profile.
    Score range: 25–95.
    """
    profile_text = " ".join(filter(None, [
        profile.get("current_job_title",      ""),
        profile.get("full_name",              ""),
        profile.get("current_city",           ""),
        str(profile.get("years_of_experience", "")),
    ])).lower()

    job_text = f"{job_title} {' '.join(bullet_fields or [])}".lower()

    profile_words = {
        w for w in re.findall(r"\b[a-z]{4,}\b", profile_text)
        if w not in _STOP_WORDS
    }
    job_words = [
        w for w in re.findall(r"\b[a-z]{4,}\b", job_text)
        if w not in _STOP_WORDS
    ]

    if not job_words or not profile_words:
        return 50

    matches = sum(1 for w in job_words if w in profile_words)
    raw     = matches / len(job_words)
    return min(95, int(25 + raw * 70))
