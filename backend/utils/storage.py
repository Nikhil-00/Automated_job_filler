import logging
import os
from supabase import create_client, Client
from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

_log = logging.getLogger(__name__)

# Initialize Supabase Client
_supabase: Client = None

def _get_client():
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            _log.error("Supabase Storage not configured. Missing URL or Service Key.")
            return None
        _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase

def upload_resume(user_id: int, file_name: str, file_content: bytes) -> str:
    """
    Upload a resume to Supabase Storage and return the public URL.
    """
    client = _get_client()
    if not client:
        return ""

    bucket_name = "resumes"
    file_path = f"{user_id}/{file_name}"

    try:
        # Check if bucket exists, if not, it will fail (you should create it in dashboard)
        # We use upsert=True to overwrite if user re-uploads
        client.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": "application/pdf", "x-upsert": "true"}
        )
        
        # Get public URL
        res = client.storage.from_(bucket_name).get_public_url(file_path)
        return res
    except Exception as e:
        _log.error("Failed to upload resume to Supabase: %s", e)
        return ""

def delete_resume(user_id: int, file_name: str):
    """
    Delete a resume from Supabase Storage.
    """
    client = _get_client()
    if not client:
        return
    
    bucket_name = "resumes"
    file_path = f"{user_id}/{file_name}"
    
    try:
        client.storage.from_(bucket_name).remove([file_path])
    except Exception as e:
        _log.error("Failed to delete resume from Supabase: %s", e)
