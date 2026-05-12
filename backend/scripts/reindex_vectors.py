import sys
import json
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import get_connection
from backend.utils.vector_store import upsert_candidate, upsert_job_vector
from backend.config import USER_DATA_DIR

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)


def _load_cv_data(data_folder: str) -> dict:
    if not data_folder:
        return {}
    base = USER_DATA_DIR / data_folder
    cv: dict = {}
    cv_path = base / "cv_data.json"
    if cv_path.exists():
        try:
            cv = json.loads(cv_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return cv


def reindex_all():
    _log.info("Starting full reindexing to pgvector — includes education, work exp, certs...")

    conn = get_connection()
    cur  = conn.cursor(dictionary=True)

    try:
        # Join with user_credentials to get data_folder for cv_data.json
        cur.execute(
            """
            SELECT cp.user_id, cp.cv_summary, cp.skills, uc.data_folder
            FROM   candidate_profile cp
            JOIN   user_credentials  uc ON uc.id = cp.user_id
            WHERE  cp.is_active = TRUE
            """
        )
        candidates = cur.fetchall()
        _log.info("Found %d active candidates to reindex.", len(candidates))

        for cand in candidates:
            try:
                skills = json.loads(cand["skills"]) if isinstance(cand["skills"], str) else (cand["skills"] or [])
                cv     = _load_cv_data(cand["data_folder"] or "")
                upsert_candidate(
                    cand["user_id"],
                    cand["cv_summary"] or "",
                    skills,
                    education=cv.get("education") or [],
                    work_experience=cv.get("work_experience") or [],
                    certifications=cv.get("certifications") or [],
                )
            except Exception as e:
                _log.error("Failed to reindex candidate %s: %s", cand["user_id"], e)

        # Reindex jobs
        cur.execute("SELECT id, title, description FROM job_postings WHERE is_active = TRUE")
        jobs = cur.fetchall()
        _log.info("Found %d active jobs to reindex.", len(jobs))

        for job in jobs:
            try:
                upsert_job_vector(job["id"], job["title"], job["description"])
            except Exception as e:
                _log.error("Failed to reindex job %s: %s", job["id"], e)

    finally:
        cur.close()
        conn.close()

    _log.info("Full reindexing complete!")


if __name__ == "__main__":
    reindex_all()
