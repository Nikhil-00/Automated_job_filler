"""
backend/api/cv.py
──────────────────
CV upload and profile retrieval endpoints.

POST   /api/cv/upload  — OCR + GPT parse → save to user's data folder
GET    /api/cv/profile — return user's saved profile.json
DELETE /api/cv/profile — wipe user's data folder + reset DB flag
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI

from backend.auth.routes import get_current_user
from backend.auth.service import get_user_by_id, set_user_data_folder
from backend.config import OPENAI_API_KEY, PROJECT_ROOT, USER_DATA_DIR

router    = APIRouter(tags=["cv"])
_openai   = OpenAI(api_key=OPENAI_API_KEY)
_bearer   = HTTPBearer()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_folder(email: str, first_name: str) -> Path:
    """Return (and create) the user-specific data folder path."""
    safe_name = (
        f"{email}_{first_name}"
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )
    folder = USER_DATA_DIR / safe_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _ocr_pdf(pdf_path: str) -> str:
    try:
        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor

        model  = ocr_predictor(pretrained=True)
        doc    = DocumentFile.from_pdf(pdf_path)
        result = model(doc)
        lines: list[str] = []
        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    lines.append(" ".join(w.value for w in line.words))
        return "\n".join(lines)
    except ImportError:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except ImportError:
        return ""


def _gpt_parse_resume(raw_text: str) -> dict:
    prompt = f"""You are a resume parser. Return ONLY valid JSON with exactly these keys
(use null for any field not found):

{{
  "full_name":                      "...",
  "email":                          "...",
  "phone":                          "...",
  "current_city":                   "...",
  "years_of_experience":            "...",
  "current_company":                "...",
  "current_job_title":              "...",
  "skills":                         ["...", "..."],
  "notice_period":                  "30",
  "current_salary":                 null,
  "expected_salary":                null,
  "linkedin_url":                   null,
  "github_url":                     null,
  "portfolio_url":                  null,
  "education_from_month":           "August",
  "education_from_year":            "2021",
  "education_to_month":             "May",
  "education_to_year":              "2025",
  "education_currently_attending":  false
}}

Rules:
- years_of_experience: integer or decimal as a string, e.g. "2" or "1.5"
- skills: extract ALL technical skills mentioned anywhere in the resume
- notice_period: always "30"
- current_salary / expected_salary: return null
- linkedin_url: full https://linkedin.com/in/... URL or null
- github_url: full https://github.com/... URL or null
- portfolio_url: full URL or null
- education fields: infer from graduation year if not stated

Resume text:
---
{raw_text[:4000]}
---
"""
    resp    = _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/cv/upload")
async def upload_cv(
    file: UploadFile = File(...),
    user: dict       = Depends(get_current_user),
):
    """
    Accept a CV (PDF/DOCX), OCR + GPT-parse it, save everything to the
    user's personal data folder.  Returns extracted profile summary.
    """
    user_id    = int(user["sub"])
    db_user    = get_user_by_id(user_id)
    user_dir   = _get_user_folder(db_user["email"], db_user["first_name"])

    suffix = Path(file.filename or "resume.pdf").suffix or ".pdf"
    cv_dest = user_dir / f"uploaded_cv{suffix}"

    with cv_dest.open("wb") as dst:
        shutil.copyfileobj(file.file, dst)

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copy(cv_dest, tmp.name)
        tmp_path = tmp.name

    try:
        raw_text = await asyncio.to_thread(_ocr_pdf, tmp_path)

        (user_dir / "resume_text.txt").write_text(raw_text, encoding="utf-8")

        profile            = await asyncio.to_thread(_gpt_parse_resume, raw_text)
        profile["resume_path"] = str(cv_dest)

        (user_dir / "profile.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False)
        )

        # Also write to project root so standalone scripts still work
        (PROJECT_ROOT / "resume_text.txt").write_text(raw_text, encoding="utf-8")
        (PROJECT_ROOT / "profile.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False)
        )

        # Mark user as having a data folder in DB
        folder_name = user_dir.name
        set_user_data_folder(user_id, folder_name)

        return {
            "jobTitle":          profile.get("current_job_title") or "",
            "yearsOfExperience": float(profile.get("years_of_experience") or 0),
            "skills":            profile.get("skills") or [],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        os.unlink(tmp_path)


@router.get("/api/cv/profile")
def get_profile(user: dict = Depends(get_current_user)):
    """Return the user's saved profile.json, or 404 if they haven't uploaded a CV yet."""
    user_id = int(user["sub"])
    db_user = get_user_by_id(user_id)

    if not db_user.get("data_folder"):
        raise HTTPException(status_code=404, detail="No profile found. Please upload your CV first.")

    profile_path = USER_DATA_DIR / db_user["data_folder"] / "profile.json"
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail="Profile file not found.")

    return json.loads(profile_path.read_text(encoding="utf-8"))


@router.patch("/api/cv/profile")
def update_profile(payload: dict, user: dict = Depends(get_current_user)):
    """
    Merge the provided fields into the user's saved profile.json.
    Only keys present in the payload are updated; others are left unchanged.
    """
    user_id = int(user["sub"])
    db_user = get_user_by_id(user_id)

    if not db_user.get("data_folder"):
        raise HTTPException(status_code=404, detail="No profile found. Please upload your CV first.")

    profile_path = USER_DATA_DIR / db_user["data_folder"] / "profile.json"
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail="Profile file not found.")

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile.update(payload)
    profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False))

    # Keep root-level copy in sync
    root_copy = PROJECT_ROOT / "profile.json"
    if root_copy.exists():
        root_copy.write_text(json.dumps(profile, indent=2, ensure_ascii=False))

    return {"message": "Profile updated."}


@router.delete("/api/cv/profile")
def reset_profile(user: dict = Depends(get_current_user)):
    """
    Permanently delete the user's data folder (CV, profile, resume text)
    and reset the data_folder flag in the database.
    The user account itself is preserved — only CV/profile data is wiped.
    """
    user_id = int(user["sub"])
    db_user = get_user_by_id(user_id)

    folder_name = db_user.get("data_folder")
    if folder_name:
        folder = USER_DATA_DIR / folder_name
        if folder.exists():
            shutil.rmtree(folder)

    # Clear the flag regardless of whether the folder existed on disk
    set_user_data_folder(user_id, None)

    return {"message": "Profile reset successfully. Please re-upload your CV."}
