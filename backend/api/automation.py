"""
backend/api/automation.py
──────────────────────────
Automation start + credential-verify endpoints.
All routes are JWT-protected.

POST /api/automation/start      — start a background automation run
POST /api/verify-credentials    — verify LinkedIn/Naukri credentials
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth.routes import get_current_user
from backend.auth.service import get_user_by_id
from backend.config import PROJECT_ROOT, USER_DATA_DIR
from backend.shared_state import _sessions, _sessions_lock
from backend.tools.session_logger import SessionLogger

router = APIRouter(tags=["automation"])


# ── Request models ─────────────────────────────────────────────────────────────

class _Credentials(BaseModel):
    email:    str
    password: str

class _Filters(BaseModel):
    role:            str        = "Data Scientist"
    experienceLevel: list[str] = []
    location:        str        = "India"
    jobType:         list[str]  = []
    applyType:       str        = "easy_apply"

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
    platform:    str
    credentials: _Credentials
    filters:     _Filters
    count:       int = 10
    profile:     _ProfileData
    sessionId:   str

class _VerifyRequest(BaseModel):
    email:    str
    password: str
    platform: str = "linkedin"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_real_url(value: str) -> bool:
    if not value:
        return False
    v = value.strip()
    if not v or v.startswith("[") or v.startswith("("):
        return False
    low = v.lower()
    if low in ("n/a", "na", "none", "-", "null"):
        return False
    return v.startswith("http") or "linkedin.com" in low or "github.com" in low


def _load_user_profile(user_id: int) -> dict:
    """Load the user's saved profile.json from their data folder."""
    db_user = get_user_by_id(user_id)
    if db_user.get("data_folder"):
        p = USER_DATA_DIR / db_user["data_folder"] / "profile.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    # Fallback to project-root profile.json
    p = PROJECT_ROOT / "profile.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _merge_profile(req: StartAutomationRequest, base: dict) -> dict:
    p  = req.profile
    np = p.noticePeriod.replace(" days", "").replace("Immediate", "0").strip()

    base_linkedin  = base.get("linkedin_url",  "") or ""
    base_github    = base.get("github_url",    "") or ""
    base_portfolio = base.get("portfolio_url", "") or ""

    linkedin_url  = p.linkedin if _is_real_url(p.linkedin) else (base_linkedin  if _is_real_url(base_linkedin)  else "")
    github_url    = p.github   if _is_real_url(p.github)   else (base_github    if _is_real_url(base_github)    else "")
    portfolio_url =                                              (base_portfolio if _is_real_url(base_portfolio) else "")

    base.update({k: v for k, v in {
        "full_name":           f"{p.firstName} {p.lastName}".strip() or base.get("full_name"),
        "phone":               p.phone       or base.get("phone"),
        "email":               p.email       or base.get("email"),
        "current_city":        p.location    or base.get("current_city", "Delhi"),
        "current_job_title":   p.jobTitle    or base.get("current_job_title"),
        "years_of_experience": p.experience  or base.get("years_of_experience", "1"),
        "notice_period":       np            or base.get("notice_period", "30"),
        "current_salary":      p.currentCtc  or base.get("current_salary", ""),
        "expected_salary":     p.expectedCtc or base.get("expected_salary", "700000"),
        "linkedin_url":        linkedin_url,
        "github_url":          github_url,
        "portfolio_url":       portfolio_url,
        "resume_path":         base.get("resume_path", str(next(PROJECT_ROOT.glob("uploaded_cv.*"), PROJECT_ROOT / "uploaded_cv.pdf"))),
        "current_company":     base.get("current_company", ""),
    }.items() if v is not None})

    return base


# ── Persisting logger ──────────────────────────────────────────────────────────

class _PersistingLogger(SessionLogger):
    """
    SessionLogger subclass that also writes every company() event to the
    user's applied_jobs.json file so history survives page refreshes.
    """

    def __init__(self, session_id: str, loop: asyncio.AbstractEventLoop,
                 user_id: int, platform: str, filters: _Filters) -> None:
        super().__init__(session_id, loop)
        self._user_id = user_id
        self._platform = platform
        self._role     = filters.role
        self._location = filters.location

    def company(self, data: dict) -> None:
        super().company(data)
        # Only persist actually-processed entries (applied / skipped / already_applied)
        from backend.api.jobs import append_job_entry
        entry = {
            "id":               str(uuid.uuid4()),
            "platform":         self._platform,
            "applied_at":       datetime.now(timezone.utc).isoformat(),
            "session_role":     self._role,
            "session_location": self._location,
            **data,
        }
        append_job_entry(self._user_id, entry)


# ── Workers ────────────────────────────────────────────────────────────────────

def _linkedin_worker(req: StartAutomationRequest, profile: dict, logger: SessionLogger) -> None:
    from backend.tools import linkedin_apply as la

    la.LINKEDIN_EMAIL    = req.credentials.email
    la.LINKEDIN_PASSWORD = req.credentials.password
    la.JOB_SEARCH_QUERY  = req.filters.role or "Data Scientist"
    la.JOB_LOCATION      = req.filters.location or "India"
    la.MAX_APPLICATIONS  = req.count
    la.EASY_APPLY_ONLY   = (req.filters.applyType == "easy_apply")

    # Persist merged profile to project root so standalone tools can still read it
    try:
        (PROJECT_ROOT / "profile.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass

    try:
        la.run_automation(profile, logger)
    except Exception as exc:
        err_str = str(exc)
        # If the persistent browser profile caused a login failure, wipe it and retry once
        if "login page could not be loaded" in err_str.lower() or "could not inject credentials" in err_str.lower():
            _clear_linkedin_profiles(req.credentials.email, logger)
            logger.warning("Stale browser profile detected — cleared. Retrying with a fresh session…")
            try:
                la.run_automation(profile, logger)
                return
            except Exception as exc2:
                logger.error(f"Fatal (retry): {exc2}")
                logger.fail(str(exc2))
                return
        logger.error(f"Fatal: {exc}")
        logger.fail(str(exc))


def _clear_linkedin_profiles(email: str, logger: SessionLogger | None = None) -> None:
    """
    Delete any linkedin_browser_profile_* directories in the project root.
    Called automatically when a stale/flagged profile causes login failure.
    """
    slug = re.sub(r"[^a-z0-9]", "", email.lower())[:12]
    for folder in PROJECT_ROOT.glob("linkedin_browser_profile_*"):
        if folder.is_dir():
            try:
                shutil.rmtree(folder)
                if logger:
                    logger.info(f"Deleted stale profile: {folder.name}")
            except Exception as e:
                if logger:
                    logger.warning(f"Could not delete {folder.name}: {e}")


def _naukri_worker(req: StartAutomationRequest, profile: dict, logger: SessionLogger) -> None:
    logger.info("Naukri automation starting...")
    logger.warning("Naukri full automation is coming soon.")
    logger.done("Naukri session ended.")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/api/automation/start")
async def start_automation(
    req:  StartAutomationRequest,
    user: dict = Depends(get_current_user),
):
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

    user_id = int(user["sub"])
    base    = _load_user_profile(user_id)
    profile = _merge_profile(req, base)

    loop   = asyncio.get_running_loop()
    logger = _PersistingLogger(req.sessionId, loop, user_id, req.platform, req.filters)
    target = _linkedin_worker if req.platform == "linkedin" else _naukri_worker

    threading.Thread(target=target, args=(req, profile, logger), daemon=True).start()
    return {"status": "started", "sessionId": req.sessionId}


class _PrintLogger:
    """
    Minimal logger that satisfies linkedin_apply's `if _logger is None` guards
    without requiring a live WebSocket session.  Prevents input() blocking.
    """
    def info    (self, m: str) -> None: print(f"[verify/info]    {m}")
    def found   (self, m: str) -> None: print(f"[verify/found]   {m}")
    def success (self, m: str) -> None: print(f"[verify/success] {m}")
    def error   (self, m: str) -> None: print(f"[verify/error]   {m}")
    def warning (self, m: str) -> None: print(f"[verify/warn]    {m}")
    def progress(self, *_)    -> None: pass
    def screenshot(self, *_)  -> None: pass
    def company (self, *_)    -> None: pass
    def cost    (self, *_)    -> None: pass
    def done    (self, m: str = "") -> None: print(f"[verify/done]    {m}")
    def fail    (self, m: str = "") -> None: print(f"[verify/fail]    {m}")


def _verify_linkedin_credentials(email: str, password: str) -> dict:
    """
    Open a VISIBLE browser window, attempt LinkedIn login, and return status.

    Running non-headless means:
      - LinkedIn is less likely to trigger bot detection
      - If a security checkpoint appears, the user sees the browser window
        and can complete the check manually — then we detect the resolved state
    """
    from playwright.sync_api import sync_playwright
    from backend.tools import linkedin_apply as la

    la.LINKEDIN_EMAIL    = email
    la.LINKEDIN_PASSWORD = password

    # Set a real logger so linkedin_apply never calls input() — which would
    # block the thread-pool worker indefinitely in a server context.
    _prev_logger  = la._logger
    la._logger    = _PrintLogger()

    result = {"status": "failed", "message": "Could not open browser."}
    try:
        with sync_playwright() as p:
            # Non-headless: user can see and interact with any security check
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
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
            page   = context.new_page()
            status = la.login_linkedin(page)

            if status == "success":
                result = {"status": "success", "message": "Login successful!"}

            elif status == "wrong_credentials":
                result = {
                    "status":  "wrong_credentials",
                    "message": "Wrong email or password. Please check your credentials.",
                }

            elif status == "checkpoint":
                # Browser is still open — wait up to 60 s for the user to
                # complete the security check, then re-check the URL.
                import time
                deadline = time.time() + 60
                resolved = False
                while time.time() < deadline:
                    time.sleep(3)
                    try:
                        url = page.url
                        if any(x in url for x in ("feed", "/in/", "mynetwork", "jobs", "home")):
                            resolved = True
                            break
                    except Exception:
                        break

                if resolved:
                    result = {"status": "success", "message": "Login successful after security check!"}
                else:
                    result = {
                        "status":  "checkpoint",
                        "message": (
                            "LinkedIn requires a security check. "
                            "A browser window opened on your screen — "
                            "please complete the verification there, then click Connect again."
                        ),
                    }

            else:
                result = {
                    "status":  "failed",
                    "message": "LinkedIn login page could not be loaded. Check your internet connection.",
                }

            try:
                browser.close()
            except Exception:
                pass

    except Exception as exc:
        result = {"status": "failed", "message": f"Browser error: {exc}"}
    finally:
        la._logger = _prev_logger   # always restore

    return result


@router.post("/api/verify-credentials")
async def verify_credentials(
    req:  _VerifyRequest,
    user: dict = Depends(get_current_user),
):
    """Verify platform credentials without starting full automation."""
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    loop   = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, _verify_linkedin_credentials, req.email, req.password
    )

    if result["status"] == "wrong_credentials":
        raise HTTPException(status_code=401, detail=result["message"])
    if result["status"] in ("failed", "checkpoint"):
        raise HTTPException(status_code=400, detail=result["message"])

    return {"status": "success", "message": result["message"]}
