"""
server.py
─────────────────────────────────────────────────────────────────────────────
FastAPI backend for AutoApply AI.

Endpoints
──────────
  POST /api/cv/upload           Accept resume → OCR + GPT → extracted fields
  WS   /ws/{session_id}         Stream real-time automation logs to the browser
  POST /api/automation/start    Start LinkedIn / Naukri run in a background thread

Run
────
  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

SCRIPT_DIR    = Path(__file__).parent
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
_openai       = OpenAI(api_key=OPENAI_KEY)

app = FastAPI(title="AutoApply AI", version="1.0.0")

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory session registry ───────────────────────────────────────────────
# Maps session_id → asyncio.Queue[str].  The WebSocket reads from the queue;
# the Playwright thread writes to it via asyncio.run_coroutine_threadsafe().
_sessions: dict[str, asyncio.Queue] = {}
_sessions_lock = threading.Lock()


# ═════════════════════════════════════════════════════════════════════════════
# Logger  (used inside the Playwright background thread)
# ═════════════════════════════════════════════════════════════════════════════

class SessionLogger:
    """Thread-safe logger that puts JSON messages on the session's asyncio Queue."""

    def __init__(self, session_id: str, loop: asyncio.AbstractEventLoop) -> None:
        self._sid     = session_id
        self._loop    = loop
        self._counter = 0

    # ── internal ──────────────────────────────────────────────────────────────

    def _enqueue(self, payload: dict) -> None:
        with _sessions_lock:
            q = _sessions.get(self._sid)
        if q is None:
            return
        asyncio.run_coroutine_threadsafe(q.put(json.dumps(payload)), self._loop)

    def _log(self, message: str, log_type: str) -> None:
        self._counter += 1
        self._enqueue({
            "type": "log",
            "payload": {
                "id":        self._counter,
                "message":   message,
                "logType":   log_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })
        print(f"[{log_type.upper():7s}] {message}")

    # ── public log helpers ────────────────────────────────────────────────────

    def info   (self, msg: str) -> None: self._log(msg, "info")
    def found  (self, msg: str) -> None: self._log(msg, "found")
    def success(self, msg: str) -> None: self._log(msg, "success")
    def error  (self, msg: str) -> None: self._log(msg, "error")
    def warning(self, msg: str) -> None: self._log(msg, "warning")

    def progress(self, current: int, total: int) -> None:
        self._enqueue({"type": "progress", "payload": {"current": current, "total": total}})

    def screenshot(self, b64_jpeg: str) -> None:
        """Send a browser screenshot frame (base64 JPEG) to the frontend."""
        self._enqueue({"type": "screenshot", "payload": {"data": b64_jpeg}})

    def company(self, data: dict) -> None:
        """Send structured company result (applied / skipped / already_applied)."""
        self._enqueue({"type": "company", "payload": data})

    def cost(self, data: dict) -> None:
        """Send GPT token/cost summary at the end of a run."""
        self._enqueue({"type": "cost", "payload": data})

    def done(self, message: str = "Automation complete!") -> None:
        self._enqueue({"type": "completed", "payload": {"message": message}})

    def fail(self, message: str) -> None:
        self._enqueue({"type": "error", "payload": {"message": message}})


# ═════════════════════════════════════════════════════════════════════════════
# WebSocket endpoint  —  /ws/{session_id}
# ═════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str) -> None:
    await ws.accept()

    q: asyncio.Queue = asyncio.Queue()
    with _sessions_lock:
        _sessions[session_id] = q

    try:
        while True:
            try:
                # Block up to 1 s so we can still catch disconnects quickly
                message = await asyncio.wait_for(q.get(), timeout=1.0)
                await ws.send_text(message)

                # Stop reading once the session is over
                parsed = json.loads(message)
                if parsed.get("type") in ("completed", "error"):
                    break

            except asyncio.TimeoutError:
                # Keepalive ping (client-side can ignore it)
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        with _sessions_lock:
            _sessions.pop(session_id, None)


# ═════════════════════════════════════════════════════════════════════════════
# CV upload  —  POST /api/cv/upload
# ═════════════════════════════════════════════════════════════════════════════

def _ocr_pdf(pdf_path: str) -> str:
    """Extract plain text from a PDF using doctr (falls back to pdfplumber)."""
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
- skills: extract ALL technical skills mentioned anywhere in the resume —
  programming languages, frameworks, tools, platforms, concepts, cloud services.
  Do NOT limit to 8. Return every skill you find.
- notice_period: always "30" regardless of what the resume says
- current_salary / expected_salary: return null — salary is almost never in a resume
- linkedin_url: return the FULL URL (starting with https://linkedin.com/in/...) if
  found verbatim in the resume text. If you only see placeholder text like
  "[Linkedin]", "(LinkedIn)", "LinkedIn Profile", or a section header — return null.
- github_url: same rule — full https://github.com/... URL or null.
- portfolio_url: same rule — full URL or null.
- education_from_month: full month name (e.g. "August") when the candidate's
  highest degree started. Infer from graduation year and typical course duration
  if not stated explicitly.
- education_from_year: 4-digit year as a string when the degree started.
- education_to_month: full month name when the degree ended / expected to end.
- education_to_year: 4-digit year as a string when the degree ended / will end.
- education_currently_attending: true if the candidate is still studying, false
  if they have already graduated.

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


@app.post("/api/cv/upload")
async def upload_cv(file: UploadFile = File(...)):
    """
    Accept a resume (PDF / DOCX).
    Returns: { jobTitle, yearsOfExperience, skills }
    Side-effects: saves resume_text.txt and profile.json for the automation.
    """
    suffix = Path(file.filename or "resume.pdf").suffix or ".pdf"

    # Save uploaded file permanently so Playwright can upload it to job portals
    cv_dest = SCRIPT_DIR / f"uploaded_cv{suffix}"
    with cv_dest.open("wb") as dst:
        shutil.copyfileobj(file.file, dst)

    # Also write to a temp path for OCR (avoids touching the permanent file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copy(cv_dest, tmp.name)
        tmp_path = tmp.name

    try:
        raw_text = await asyncio.to_thread(_ocr_pdf, tmp_path)

        # Persist raw text so linkedin_apply.py can use it for AI answers
        (SCRIPT_DIR / "resume_text.txt").write_text(raw_text, encoding="utf-8")

        profile  = await asyncio.to_thread(_gpt_parse_resume, raw_text)
        profile["resume_path"] = str(cv_dest)

        # Persist profile.json as the base profile
        (SCRIPT_DIR / "profile.json").write_text(json.dumps(profile, indent=2))

        return {
            "jobTitle":          profile.get("current_job_title") or "",
            "yearsOfExperience": float(profile.get("years_of_experience") or 0),
            "skills":            profile.get("skills") or [],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        os.unlink(tmp_path)


# ═════════════════════════════════════════════════════════════════════════════
# Automation start  —  POST /api/automation/start
# ═════════════════════════════════════════════════════════════════════════════

class _Credentials(BaseModel):
    email:    str
    password: str

class _Filters(BaseModel):
    role:            str        = "Data Scientist"
    experienceLevel: list[str] = []
    location:        str        = "India"
    jobType:         list[str]  = []
    applyType:       str        = "easy_apply"   # "easy_apply" | "external"

class _ProfileData(BaseModel):
    firstName:    str = ""
    lastName:     str = ""
    phone:        str = ""
    email:        str = ""
    currentCtc:   str = ""
    expectedCtc:  str = ""
    location:     str = ""
    jobTitle:     str = ""
    noticePeriod: str = "30"
    experience:   str = "1"
    linkedin:     str = ""
    github:       str = ""

class StartAutomationRequest(BaseModel):
    platform:    str              # "linkedin" | "naukri"
    credentials: _Credentials
    filters:     _Filters
    count:       int = 10
    profile:     _ProfileData
    sessionId:   str


def _is_real_url(value: str) -> bool:
    """
    Return True only if ``value`` looks like an actual URL.
    Rejects GPT-generated placeholders such as "[Linkedin]", "(GitHub)",
    "LinkedIn Profile", "N/A", bare section headers, etc.
    """
    if not value:
        return False
    v = value.strip()
    if not v or v.startswith("[") or v.startswith("("):
        return False
    low = v.lower()
    if low in ("n/a", "na", "none", "-", "null"):
        return False
    # Must contain a recognisable domain or start with http
    return (
        v.startswith("http")
        or "linkedin.com" in low
        or "github.com"   in low
    )


def _merge_profile(req: StartAutomationRequest) -> dict:
    """
    Merge the saved profile.json (from CV upload) with values entered in the UI.
    Priority order (highest → lowest):
      1. UI fields filled in by the user
      2. CV-extracted fields from profile.json
      3. Hardcoded sensible defaults
    """
    base: dict = {}
    profile_path = SCRIPT_DIR / "profile.json"
    if profile_path.exists():
        try:
            base = json.loads(profile_path.read_text())
        except Exception:
            pass

    p  = req.profile
    np = p.noticePeriod.replace(" days", "").replace("Immediate", "0").strip()

    # For URL fields: use UI value if real, else CV-extracted if real, else empty.
    # This prevents GPT placeholder text like "[Linkedin]" from being used.
    base_linkedin  = base.get("linkedin_url",  "") or ""
    base_github    = base.get("github_url",    "") or ""
    base_portfolio = base.get("portfolio_url", "") or ""

    linkedin_url  = p.linkedin if _is_real_url(p.linkedin)  else (base_linkedin  if _is_real_url(base_linkedin)  else "")
    github_url    = p.github   if _is_real_url(p.github)    else (base_github    if _is_real_url(base_github)    else "")
    portfolio_url =                                               (base_portfolio if _is_real_url(base_portfolio) else "")

    base.update({k: v for k, v in {
        "full_name":           f"{p.firstName} {p.lastName}".strip() or base.get("full_name"),
        "phone":               p.phone       or base.get("phone"),
        "email":               p.email       or base.get("email"),
        "current_city":        p.location    or base.get("current_city", "Delhi"),
        "current_job_title":   p.jobTitle    or base.get("current_job_title"),
        "years_of_experience": p.experience  or base.get("years_of_experience", "1"),
        "notice_period":       np            or base.get("notice_period", "30"),
        # Both salary fields now flow through correctly
        "current_salary":      p.currentCtc  or base.get("current_salary", ""),
        "expected_salary":     p.expectedCtc or base.get("expected_salary", "700000"),
        "linkedin_url":        linkedin_url,
        "github_url":          github_url,
        "portfolio_url":       portfolio_url,
        "resume_path":         str(next(SCRIPT_DIR.glob("uploaded_cv.*"), SCRIPT_DIR / "uploaded_cv.pdf")),
        "current_company":     base.get("current_company", ""),
    }.items() if v is not None})

    return base


def _linkedin_worker(req: StartAutomationRequest, logger: SessionLogger) -> None:
    """Runs in a daemon thread — sets linkedin_apply module config and calls run_automation."""
    import linkedin_apply as la

    la.LINKEDIN_EMAIL    = req.credentials.email
    la.LINKEDIN_PASSWORD = req.credentials.password
    la.JOB_SEARCH_QUERY  = req.filters.role or "Data Scientist"
    la.JOB_LOCATION      = req.filters.location or "India"
    la.MAX_APPLICATIONS  = req.count
    la.EASY_APPLY_ONLY   = (req.filters.applyType == "easy_apply")

    profile = _merge_profile(req)

    # Persist the merged profile so every subsequent run and tool that reads
    # profile.json (e.g. standalone scripts) gets the latest UI-entered values
    # (LinkedIn URL, GitHub URL, salary, etc.) rather than the stale CV parse.
    try:
        (SCRIPT_DIR / "profile.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass  # non-fatal — automation still runs with the in-memory profile

    try:
        la.run_automation(profile, logger)
    except Exception as exc:
        logger.error(f"Fatal: {exc}")
        logger.fail(str(exc))


def _naukri_worker(req: StartAutomationRequest, logger: SessionLogger) -> None:
    logger.info("Naukri automation starting...")
    logger.warning("Naukri full automation is coming soon.")
    logger.done("Naukri session ended.")


class _VerifyRequest(BaseModel):
    email:    str
    password: str
    platform: str = "linkedin"   # future: "naukri"


def _verify_linkedin_credentials(email: str, password: str) -> dict:
    """
    Spin up a headless browser, attempt to log in with the given credentials,
    and return the result without starting any automation.

    Returns {"status": "success"|"wrong_credentials"|"checkpoint"|"failed",
             "message": "<human-readable explanation>"}
    """
    from playwright.sync_api import sync_playwright
    import linkedin_apply as la

    # Temporarily override module-level credentials for the login call
    la.LINKEDIN_EMAIL    = email
    la.LINKEDIN_PASSWORD = password

    result = {"status": "failed", "message": "Could not open browser."}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            status = la.login_linkedin(page)

            if status == "success":
                result = {"status": "success", "message": "Login successful!"}
            elif status == "wrong_credentials":
                result = {
                    "status": "wrong_credentials",
                    "message": "Wrong email or password. Please check your credentials.",
                }
            elif status == "checkpoint":
                result = {
                    "status": "checkpoint",
                    "message": (
                        "LinkedIn requires a security check (CAPTCHA or 2FA). "
                        "Please log in manually in your browser once to clear it."
                    ),
                }
            else:
                result = {
                    "status": "failed",
                    "message": "LinkedIn login page could not be loaded. Check your internet connection.",
                }

            try:
                browser.close()
            except Exception:
                pass

    except Exception as exc:
        result = {"status": "failed", "message": f"Browser error: {exc}"}

    return result


@app.post("/api/verify-credentials")
async def verify_credentials(req: _VerifyRequest):
    """
    Verify LinkedIn (or Naukri) credentials without starting automation.
    Runs a headless browser login and returns success/failure immediately.
    """
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    loop = asyncio.get_running_loop()

    # Run the blocking Playwright check in a thread pool so it doesn't
    # block the FastAPI event loop.
    result = await loop.run_in_executor(
        None, _verify_linkedin_credentials, req.email, req.password
    )

    if result["status"] == "wrong_credentials":
        raise HTTPException(status_code=401, detail=result["message"])

    if result["status"] in ("failed", "checkpoint"):
        raise HTTPException(status_code=400, detail=result["message"])

    return {"status": "success", "message": result["message"]}


@app.post("/api/automation/start")
async def start_automation(req: StartAutomationRequest):
    """
    Kick off automation in a background thread.
    Logs stream to the browser via WebSocket at /ws/{req.sessionId}.
    """
    with _sessions_lock:
        if req.sessionId not in _sessions:
            raise HTTPException(
                status_code=400,
                detail="WebSocket session not found. Connect to /ws/{sessionId} first.",
            )

    loop   = asyncio.get_running_loop()
    logger = SessionLogger(req.sessionId, loop)
    target = _linkedin_worker if req.platform == "linkedin" else _naukri_worker

    threading.Thread(target=target, args=(req, logger), daemon=True).start()

    return {"status": "started", "sessionId": req.sessionId}


# ─── Dev entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
