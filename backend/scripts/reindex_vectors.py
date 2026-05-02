import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import get_connection
from backend.utils.vector_store import upsert_candidate, upsert_job_vector
import logging

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

def reindex_all():
    _log.info("Starting full reindexing to Supabase/pgvector...")
    
    conn = get_connection()
    cur  = conn.cursor(dictionary=True)
    
    try:
        # 1. Reindex Candidates
        cur.execute("SELECT user_id, cv_summary, skills FROM candidate_profile WHERE is_active = TRUE")
        candidates = cur.fetchall()
        _log.info("Found %d active candidates to reindex.", len(candidates))
        
        for cand in candidates:
            try:
                import json
                skills = json.loads(cand['skills']) if isinstance(cand['skills'], str) else cand['skills']
                upsert_candidate(cand['user_id'], cand['cv_summary'], skills)
            except Exception as e:
                _log.error("Failed to reindex candidate %s: %s", cand['user_id'], e)

        # 2. Reindex Jobs
        cur.execute("SELECT id, title, description FROM job_postings WHERE is_active = TRUE")
        jobs = cur.fetchall()
        _log.info("Found %d active jobs to reindex.", len(jobs))
        
        for job in jobs:
            try:
                upsert_job_vector(job['id'], job['title'], job['description'])
            except Exception as e:
                _log.error("Failed to reindex job %s: %s", job['id'], e)

    finally:
        cur.close()
        conn.close()

    _log.info("Full reindexing complete!")

if __name__ == "__main__":
    reindex_all()
