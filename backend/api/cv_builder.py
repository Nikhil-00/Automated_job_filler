"""
backend/api/cv_builder.py
──────────────────────────
CV Builder endpoints.

POST /api/cv/parse         — OCR (doctr → pdfplumber fallback) + Groq parse.
                             Returns structured cv_data JSON; does NOT save.
GET  /api/cv/builder       — Return saved cv_data.json (404 = new/incomplete user).
POST /api/cv/builder/save  — Save cv_data + generate ATS PDF + back-fill profile.json.
GET  /api/cv/builder/pdf   — Stream the generated ATS PDF for download.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.auth.routes  import get_current_user
from backend.auth.service import get_user_by_id, set_user_data_folder
from backend.config       import USER_DATA_DIR

router  = APIRouter(tags=["cv-builder"])
_log    = logging.getLogger(__name__)

_MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB


# ── Folder helper ──────────────────────────────────────────────────────────────

def _user_folder(email: str, first_name: str) -> Path:
    safe = (
        f"{email}_{first_name}"
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )
    folder = USER_DATA_DIR / safe
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ── OCR helper ─────────────────────────────────────────────────────────────────

def _ocr(pdf_path: str) -> str:
    """Extract text from PDF. Tries doctr first, falls back to pdfplumber."""
    # doctr — preferred (layout-aware)
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
        text = "\n".join(lines).strip()
        if text:
            _log.info("[cv_builder] doctr OCR succeeded (%d chars).", len(text))
            return text
    except Exception as exc:
        _log.debug("[cv_builder] doctr unavailable: %s", exc)

    # pdfplumber — fallback
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        _log.info("[cv_builder] pdfplumber fallback (%d chars).", len(text))
        return text
    except Exception as exc:
        _log.error("[cv_builder] pdfplumber also failed: %s", exc)
        return ""


# ── POST /api/cv/parse ─────────────────────────────────────────────────────────

@router.post("/api/cv/parse")
async def parse_cv(
    file: UploadFile = File(...),
    _user: dict      = Depends(get_current_user),
):
    """
    Upload a PDF → OCR with doctr → structured parse with Groq.
    Returns cv_data JSON without saving to disk.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    contents = await file.read()
    if len(contents) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        raw_text = await asyncio.to_thread(_ocr, tmp_path)
        if not raw_text:
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from this PDF. Please fill the form manually.",
            )

        from backend.services.groq_cv_parser import parse_resume_with_groq
        cv_data = await asyncio.to_thread(parse_resume_with_groq, raw_text)
        return cv_data

    except HTTPException:
        raise
    except Exception as exc:
        _log.error("[cv_builder] parse error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Parse failed: {exc}")
    finally:
        os.unlink(tmp_path)


# ── GET /api/cv/builder ────────────────────────────────────────────────────────

@router.get("/api/cv/builder")
def get_cv_builder(user: dict = Depends(get_current_user)):
    """Return saved cv_data.json, or 404 if the user has not completed the CV Builder."""
    user_id = int(user["sub"])
    db_user = get_user_by_id(user_id)

    if not db_user.get("data_folder"):
        raise HTTPException(status_code=404, detail="CV not found.")

    cv_path = USER_DATA_DIR / db_user["data_folder"] / "cv_data.json"
    if not cv_path.exists():
        raise HTTPException(status_code=404, detail="CV not found.")

    return json.loads(cv_path.read_text(encoding="utf-8"))


# ── POST /api/cv/builder/save ─────────────────────────────────────────────────

@router.post("/api/cv/builder/save")
async def save_cv_builder(
    payload: dict,
    user:    dict = Depends(get_current_user),
):
    """
    Persist cv_data, generate ATS PDF, and back-fill profile.json for automation.
    """
    user_id = int(user["sub"])
    db_user = get_user_by_id(user_id)

    folder = _user_folder(db_user["email"], db_user["first_name"])

    # ── Save cv_data.json ──────────────────────────────────────────────────────
    cv_path = folder / "cv_data.json"
    cv_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Generate ATS PDF ───────────────────────────────────────────────────────
    pdf_ready = False
    try:
        from backend.services.cv_pdf_generator import generate_pdf, generate_pdf_filename
        pdf_bytes = await asyncio.to_thread(generate_pdf, payload)
        named_pdf = generate_pdf_filename(payload)
        (folder / named_pdf).write_bytes(pdf_bytes)
        (folder / "ats_cv.pdf").write_bytes(pdf_bytes)   # stable filename
        pdf_ready = True
        _log.info("[cv_builder] ATS PDF generated for user %d.", user_id)
    except Exception as exc:
        _log.error("[cv_builder] PDF generation failed for user %d: %s", user_id, exc)

    # ── Back-fill profile.json (keeps automation working) ─────────────────────
    contact = payload.get("contact") or {}
    skills  = (payload.get("skills") or {}).get("technical") or []
    work    = payload.get("work_experience") or []

    profile: dict = {
        "full_name":             (contact.get("name") or "").strip(),
        "email":                 contact.get("email") or db_user.get("email", ""),
        "phone":                 (contact.get("phone") or "").strip(),
        "current_city":          (contact.get("location") or "").strip(),
        "linkedin_url":          contact.get("linkedin") or None,
        "github_url":            contact.get("github") or None,
        "portfolio_url":         contact.get("portfolio") or None,
        "skills":                skills,
        "current_job_title":     work[0].get("title", "") if work else "",
        "current_company":       work[0].get("company", "") if work else "",
        "years_of_experience":   str(len(work)) if work else "0",
        "notice_period":         "30",
        "current_salary":        None,
        "expected_salary":       None,
    }

    # Preserve user-set salary / notice fields from existing profile
    existing_path = folder / "profile.json"
    if existing_path.exists():
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            for k in ("current_salary", "expected_salary", "notice_period"):
                if existing.get(k):
                    profile[k] = existing[k]
        except Exception:
            pass

    existing_path.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── Register data_folder in DB if first time ───────────────────────────────
    if not db_user.get("data_folder"):
        set_user_data_folder(user_id, folder.name)

    return {"status": "saved", "pdf_ready": pdf_ready}


# ── GET /api/cv/builder/pdf ───────────────────────────────────────────────────

@router.get("/api/cv/builder/pdf")
def download_cv_pdf(user: dict = Depends(get_current_user)):
    """Stream the user's generated ATS CV PDF."""
    user_id = int(user["sub"])
    db_user = get_user_by_id(user_id)

    if not db_user.get("data_folder"):
        raise HTTPException(status_code=404, detail="No CV found.")

    pdf_path = USER_DATA_DIR / db_user["data_folder"] / "ats_cv.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not generated yet. Please save your CV first.")

    fname = f"{db_user['first_name']}_{db_user['last_name']}_ATS_CV.pdf"
    return Response(
        content=pdf_path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
