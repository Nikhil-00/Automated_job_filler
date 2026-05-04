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

# Minimum AI score to consider a candidate a "match" for the role
MIN_MATCH_SCORE = 35


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
                   FROM job_postings WHERE id = %s AND is_active = TRUE""",
                (job_id,),
            )
            job = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if not job:
            return

        # 2. Semantic Search: Find candidates by meaning, not just keywords
        try:
            from backend.utils.vector_store import search_candidates
            results = search_candidates(job["title"], limit=150)
            candidate_ids = [cid for cid, score in results]
        except Exception as v_exc:
            _log.error("[matching] semantic search failed: %s", v_exc)
            return

        if not candidate_ids:
            _log.info("[matching] no candidates found via semantic search for job %s", job_id)
            return

        _log.info("[matching] found %d candidates semantically; fetching profiles…", len(candidate_ids))

        # 3. Fetch full profiles for the discovered candidates
        placeholders = ", ".join(["%s"] * len(candidate_ids))
        conn = get_connection()
        cur  = conn.cursor(dictionary=True)
        try:
            cur.execute(
                f"""
                SELECT
                    user_id,
                    cv_summary,
                    years_experience,
                    expected_ctc,
                    skills
                FROM candidate_profile
                WHERE is_active = TRUE
                  AND user_id IN ({placeholders})
                """,
                candidate_ids,
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
        from backend.config import GROQ_API_KEY, USER_DATA_DIR
        if not GROQ_API_KEY:
            _bulk_insert(job_id, [(c["user_id"], 50, "AI scoring not configured.") for c in candidates])
            return

        from groq import Groq as _Groq
        client  = _Groq(api_key=GROQ_API_KEY)
        jd_text = f"JOB TITLE: {job['title']}\n\nDESCRIPTION:\n{(job.get('description') or '')[:2500]}"
        scored: list[tuple[int, int, str]] = []

        for cand in candidates:
            try:
                # Load full CV data to give AI project context
                user_id = cand["user_id"]
                full_cv = {}
                try:
                    # Try to find the user's data folder to get projects
                    conn_tmp = get_connection()
                    cur_tmp  = conn_tmp.cursor(dictionary=True)
                    cur_tmp.execute("SELECT data_folder FROM user_credentials WHERE id = %s", (user_id,))
                    u_row = cur_tmp.fetchone()
                    cur_tmp.close()
                    conn_tmp.close()

                    if u_row and u_row.get("data_folder"):
                        cv_path = USER_DATA_DIR / u_row["data_folder"] / "cv_data.json"
                        if cv_path.exists():
                            full_cv = json.loads(cv_path.read_text(encoding="utf-8"))
                except: pass

                projects_text = ""
                for p in full_cv.get("projects", []):
                    projects_text += f"- {p.get('name')}: {p.get('description')} (Tech: {p.get('tech_stack')})\n"

                prompt = f"""
ROLE: Senior Technical Recruiter
TASK: Evaluate the candidate's fit for the following job.

{jd_text}

CANDIDATE DATA:
- Summary: {cand.get('cv_summary') or 'N/A'}
- Skills: {cand.get('skills') or '[]'}
- Experience: {cand.get('years_experience', 0)} years
- Key Projects:
{projects_text or "No specific projects listed."}

SCORING CRITERIA:
1. HOLISTIC MATCH: Do not just count keywords. If a candidate hasn't listed "LangChain" but has built "Agentic AI platforms" or "LLM-based automation," they likely have the equivalent skill.
2. PROJECT VALUE: High-complexity projects (like building automation platforms, OCR systems, or BI chatbots) should be weighted heavily.
3. SENIORITY: Consider if the projects demonstrate enough autonomy for an 'Engineer' title, regardless of the 'Intern' label.

Return ONLY valid JSON:
{{"score": <0-100>, "reason": "<one concise sentence explaining the score focusing on project/skill alignment>"}}
"""

                resp   = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": "You are a highly intuitive technical recruiter who prioritizes project complexity and inferred skills over keyword checklists. Return only valid JSON."},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=150,
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
        # 1. Filter out candidates below the threshold
        valid_scored = [(uid, s, r) for uid, s, r in scored if s >= MIN_MATCH_SCORE]
        
        # 2. Upsert valid matches
        for user_id, score, reason in valid_scored:
            cur.execute(
                """
                INSERT INTO candidate_job_matches
                    (job_id, user_id, ai_score, ai_reasoning, shortlist_status, matched_at)
                VALUES (%s, %s, %s, %s, 'pending', %s)
                ON CONFLICT (job_id, user_id) DO UPDATE SET
                    ai_score         = EXCLUDED.ai_score,
                    ai_reasoning     = EXCLUDED.ai_reasoning,
                    matched_at       = EXCLUDED.matched_at
                """,
                (job_id, user_id, score, reason, now),
            )
            
        # 3. Cleanup: If any previously matched candidates now fall below threshold (due to re-matching), remove them
        all_candidate_ids = [uid for uid, s, r in scored]
        if all_candidate_ids:
            placeholders = ", ".join(["%s"] * len(all_candidate_ids))
            cur.execute(
                f"""
                DELETE FROM candidate_job_matches 
                WHERE job_id = %s 
                  AND user_id IN ({placeholders})
                  AND ai_score < %s
                """,
                [job_id] + all_candidate_ids + [MIN_MATCH_SCORE]
            )
            
        conn.commit()
    finally:
        cur.close()
        conn.close()
