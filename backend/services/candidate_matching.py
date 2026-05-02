"""
backend/services/candidate_matching.py
────────────────────────────────────────
SQL-based candidate matching for job postings.
Called in a background thread after a new job is posted.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from backend.database import get_connection

_log = logging.getLogger(__name__)

_TITLE_STOPWORDS = {
    "senior", "junior", "lead", "staff", "principal", "associate",
    "and", "the", "of", "for", "with", "at", "in", "a", "an",
}


def _title_words(title: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]+", title.lower())
    return [w for w in words if len(w) > 2 and w not in _TITLE_STOPWORDS]


def run_matching(job_id: str) -> None:
    """
    Find candidates that match the job posting and store AI scores.
    Runs in a background thread — safe to call and forget.
    """
    try:
        # 1. Fetch job details
        conn = get_connection()
        cur  = conn.cursor(dictionary=True)
        try:
            cur.execute(
                """SELECT id, title, description, experience_min, experience_max,
                          salary_max, salary_currency
                   FROM job_postings WHERE id = %s AND is_active = 1""",
                (job_id,),
            )
            job = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if not job:
            return

        words = _title_words(job["title"])
        if not words:
            return

        # 2. SQL filter: role keyword match only — experience/CTC handled by AI scorer
        like_conditions = " OR ".join(["ctr.job_title LIKE %s"] * len(words))
        like_params = [f"%{w}%" for w in words]

        _log.info("[matching] job=%r words=%s", job["title"], words)

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)
        try:
            cur.execute(
                f"""
                SELECT DISTINCT
                    cp.user_id,
                    cp.cv_summary,
                    cp.years_experience,
                    cp.expected_ctc,
                    cp.skills
                FROM candidate_profile cp
                JOIN candidate_target_roles ctr ON ctr.candidate_id = cp.user_id
                WHERE cp.is_active = 1
                  AND ({like_conditions})
                LIMIT 200
                """,
                like_params,
            )
            candidates = cur.fetchall()
        finally:
            cur.close()
            conn.close()

        if not candidates:
            _log.info(
                "[matching] no candidates for job %s | title=%r words=%s",
                job_id, job["title"], words,
            )
            return

        _log.info("[matching] %d candidates for job %s — scoring…", len(candidates), job_id)

        # 3. AI score each candidate
        from backend.config import GROQ_API_KEY
        if not GROQ_API_KEY:
            _bulk_insert(job_id, [(c["user_id"], 50, "AI scoring not configured.") for c in candidates])
            return

        from groq import Groq as _Groq
        client  = _Groq(api_key=GROQ_API_KEY)
        jd_text = f"Job Title: {job['title']}\n\n{(job.get('description') or '')[:2000]}"
        scored: list[tuple[int, int, str]] = []

        for cand in candidates:
            try:
                prompt = f"""{jd_text}

CANDIDATE SUMMARY: {cand.get('cv_summary') or 'Not available'}
SKILLS: {cand.get('skills') or '[]'}
EXPERIENCE: {cand.get('years_experience', 0)} years

Score this candidate 0-100 for job fit.
Return ONLY valid JSON: {{"score": <0-100>, "reason": "<one sentence>"}}"""

                resp   = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": "You are a recruiter. Return only valid JSON."},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=100,
                    response_format={"type": "json_object"},
                )
                data   = json.loads(resp.choices[0].message.content)
                score  = max(0, min(100, int(data.get("score", 50))))
                reason = str(data.get("reason", ""))[:400]
                scored.append((cand["user_id"], score, reason))
            except Exception as exc:
                _log.warning("[matching] score failed for user %s: %s", cand["user_id"], exc)
                scored.append((cand["user_id"], 50, "Scoring failed."))

        _bulk_insert(job_id, scored)
        _log.info("[matching] done — %d scored for job %s", len(scored), job_id)

    except Exception as exc:
        _log.error("[matching] run_matching failed for job %s: %s", job_id, exc)


def _bulk_insert(job_id: str, scored: list[tuple[int, int, str]]) -> None:
    if not scored:
        return
    now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cur  = conn.cursor()
    try:
        for user_id, score, reason in scored:
            cur.execute(
                """
                INSERT INTO candidate_job_matches
                    (job_id, user_id, ai_score, ai_reasoning, shortlist_status, matched_at)
                VALUES (%s, %s, %s, %s, 'pending', %s)
                ON DUPLICATE KEY UPDATE
                    ai_score         = VALUES(ai_score),
                    ai_reasoning     = VALUES(ai_reasoning),
                    matched_at       = VALUES(matched_at)
                """,
                (job_id, user_id, score, reason, now),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()
