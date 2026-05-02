import logging
from openai import OpenAI
from backend.config import OPENAI_API_KEY, OPENAI_EMBEDDING_MODEL
from backend.database import get_connection

_log = logging.getLogger(__name__)

_o_client = OpenAI(api_key=OPENAI_API_KEY)

def _get_embedding(text: str) -> list[float]:
    """Generate embedding using OpenAI text-embedding-3-small."""
    try:
        clean_text = text.replace("\n", " ")[:8000]
        resp = _o_client.embeddings.create(
            input=[clean_text],
            model=OPENAI_EMBEDDING_MODEL
        )
        return resp.data[0].embedding
    except Exception as exc:
        _log.error("Failed to generate embedding: %s", exc)
        raise

def upsert_candidate(user_id: int, summary: str, skills: list[str] | str):
    """
    Store or update candidate vector in PostgreSQL candidate_profile table.
    """
    try:
        skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)
        text_content = f"Summary: {summary}\nSkills: {skills_str}"
        
        embedding = _get_embedding(text_content)
        
        conn = get_connection()
        cur  = conn.cursor()
        try:
            cur.execute(
                "UPDATE candidate_profile SET embedding = %s WHERE user_id = %s",
                (embedding, user_id)
            )
            conn.commit()
            _log.info("Successfully updated candidate %s vector in Postgres.", user_id)
        finally:
            cur.close()
            conn.close()
    except Exception as exc:
        _log.error("upsert_candidate failed for user %s: %s", user_id, exc)

def search_candidates(query: str, limit: int = 150) -> list[tuple[int, float]]:
    """
    Find candidates semantically similar to the query using pgvector.
    Returns a list of (user_id, score) ranked by similarity.
    Score is 1 - distance, scaled to 0-100.
    """
    try:
        query_embedding = _get_embedding(query)
        
        conn = get_connection()
        cur  = conn.cursor()
        try:
            # Postgres <=> operator is for cosine distance
            # score = (1 - distance) * 100
            cur.execute(
                """
                SELECT user_id, (1 - (embedding <=> %s::vector)) * 100 as score
                FROM candidate_profile 
                WHERE is_active = TRUE AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, limit)
            )
            rows = cur.fetchall()
            return [(r[0], float(r[1])) for r in rows]
        finally:
            cur.close()
            conn.close()
    except Exception as exc:
        _log.error("search_candidates failed for query '%s': %s", query, exc)
        return []

def upsert_job_vector(job_id: str, title: str, description: str):
    """
    Store vector for a job posting.
    """
    try:
        text_content = f"Title: {title}\nDescription: {description}"
        embedding = _get_embedding(text_content)
        
        conn = get_connection()
        cur  = conn.cursor()
        try:
            cur.execute(
                "UPDATE job_postings SET embedding = %s WHERE id = %s",
                (embedding, job_id)
            )
            conn.commit()
            _log.info("Successfully updated job %s vector in Postgres.", job_id)
        finally:
            cur.close()
            conn.close()
    except Exception as exc:
        _log.error("upsert_job_vector failed for job %s: %s", job_id, exc)
