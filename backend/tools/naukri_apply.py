"""
backend/tools/naukri_apply.py
─────────────────────────────
Automatically applies to Naukri jobs using the user's profile.json.

Flow:
  Login → Search jobs → For each job:
    → Naukri Easy Apply  OR  External ATS (Greenhouse / Lever / Workday / …)
    → Fill form → Submit

Designed to match the thread-safety pattern of linkedin_apply.py:
  • All per-run config stored in threading.local() — no module globals touched.
  • run_automation() is the only public entry point called by the server.
  • CDPScreencaster streams live browser frames to the frontend.
  • stop_event lets the server request a clean shutdown mid-run.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import threading
import random
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# ── Directory helpers ─────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)

# ── Default fallback credentials (env vars, never used for multi-user runs) ──
NAUKRI_EMAIL    = os.getenv("NAUKRI_EMAIL", "")
NAUKRI_PASSWORD = os.getenv("NAUKRI_PASSWORD", "")
JOB_SEARCH_QUERY = "Data Scientist"
JOB_LOCATION     = "India"
MAX_APPLICATIONS = 20

# ── Thread-local run state ────────────────────────────────────────────────────
# All per-run mutable state lives here so concurrent threads for different
# users never overwrite each other's credentials or counters.
_tls = threading.local()


def _tls_get(attr: str, default=None):
    return getattr(_tls, attr, default)


# Per-run accessor helpers — always read from _tls, fall back to module defaults
def _email()        -> str:  return _tls_get("email",        NAUKRI_EMAIL)
def _password()     -> str:  return _tls_get("password",     NAUKRI_PASSWORD)
def _search_query() -> str:  return _tls_get("search_query", JOB_SEARCH_QUERY)
def _location()     -> str:  return _tls_get("location",     JOB_LOCATION)
def _max_apps()     -> int:  return _tls_get("max_apps",     MAX_APPLICATIONS)


def _logger():
    return _tls_get("logger")


# ── Logging / screenshot helpers ──────────────────────────────────────────────

def _log(message: str, log_type: str = "info") -> None:
    lg = _logger()
    if lg is not None:
        getattr(lg, log_type, lg.info)(message)
    print(message)


def _human_delay(min_ms: int = 300, max_ms: int = 900) -> None:
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _screenshot(page) -> None:
    lg = _logger()
    if lg is None or not hasattr(lg, "screenshot"):
        return
    try:
        img_bytes = page.screenshot(type="jpeg", quality=55, full_page=False)
        lg.screenshot(base64.b64encode(img_bytes).decode())
    except Exception:
        pass


def _send_company(index: int, title: str, company: str, location: str,
                  status: str, reason: str = "", url: str = "") -> None:
    lg = _logger()
    if lg is not None and hasattr(lg, "company"):
        lg.company({
            "index":    index,
            "title":    title,
            "company":  company,
            "location": location,
            "status":   status,
            "reason":   reason,
            "url":      url,
        })


# ── CDPScreencaster ───────────────────────────────────────────────────────────

class CDPScreencaster:
    """
    Streams live browser frames to the frontend via Chrome DevTools Protocol.
    Identical in design to linkedin_apply.CDPScreencaster.
    """
    _MAX_FPS:   int = 10
    _QUALITY:   int = 60
    _MAX_WIDTH: int = 1280
    _MAX_HEIGHT:int = 800

    def __init__(self, page, logger) -> None:
        self._page    = page
        self._logger  = logger
        self._session = None
        self._active  = False
        self._last_ts = 0.0

    def start(self) -> None:
        if self._active:
            return
        try:
            self._session = self._page.context.new_cdp_session(self._page)
            self._session.on("Page.screencastFrame", self._on_frame)
            self._session.send("Page.startScreencast", {
                "format":        "jpeg",
                "quality":       self._QUALITY,
                "maxWidth":      self._MAX_WIDTH,
                "maxHeight":     self._MAX_HEIGHT,
                "everyNthFrame": 1,
            })
            self._active = True
            print("[CDPScreencaster] Screencast started.")
        except Exception as exc:
            print(f"[CDPScreencaster] start() failed ({exc!r}); falling back to manual screenshots.")

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        try:
            if self._session:
                self._session.send("Page.stopScreencast", {})
        except Exception:
            pass
        try:
            if self._session:
                self._session.detach()
        except Exception:
            pass
        self._session = None
        print("[CDPScreencaster] Screencast stopped.")

    def _on_frame(self, params: dict) -> None:
        session_id: int = params.get("sessionId", 0)
        self._ack(session_id)
        if not self._active or self._logger is None:
            return
        now = time.monotonic()
        if now - self._last_ts < 1.0 / self._MAX_FPS:
            return
        self._last_ts = now
        try:
            self._logger.screenshot(params["data"])
        except Exception:
            pass

    def _ack(self, session_id: int) -> None:
        try:
            if self._session:
                self._session.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            pass


# ── ATS detection ─────────────────────────────────────────────────────────────

def detect_ats(url: str) -> str:
    u = url.lower()
    if "greenhouse.io" in u or "boards.greenhouse" in u:  return "greenhouse"
    if "lever.co" in u:                                   return "lever"
    if "workday.com" in u or "myworkdayjobs.com" in u:    return "workday"
    if "smartrecruiters.com" in u:                        return "smartrecruiters"
    if "zohorecruit.com" in u or "zoho.com/recruit" in u: return "zoho"
    if "taleo.net" in u:                                  return "taleo"
    if "bamboohr.com" in u:                               return "bamboohr"
    if "icims.com" in u:                                  return "icims"
    if "keka.com" in u or "kekahr.com" in u:              return "keka"
    if "darwinbox.com" in u:                              return "darwinbox"
    if "freshteam.com" in u:                              return "freshteam"
    if "oraclecloud.com" in u or "oracle.com/careers" in u: return "oracle"
    if "apprenticeshipindia.gov.in" in u or "nats.edu.in" in u: return "skillindia"
    if "hire.trakstar.com" in u:                          return "trakstar"
    return "unknown"


# ── Page guards ───────────────────────────────────────────────────────────────

def accept_cookies(page) -> None:
    cookie_selectors = [
        "button:has-text('Accept All Cookies')",
        "button:has-text('Accept All')",
        "button:has-text('Accept Cookies')",
        "button:has-text('Accept')",
        "button:has-text('I Accept')",
        "button:has-text('Agree')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('Allow all')",
        "button#onetrust-accept-btn-handler",
        "[id*='cookie'] button",
        "[class*='consent'] button:has-text('Accept')",
    ]
    for sel in cookie_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(1)
                return
        except Exception:
            continue


def is_valid_apply_page(page, url: str) -> bool:
    u = url.lower()
    if u.endswith(".pdf"):
        return False
    bad_url_patterns = ["/search?", "/jobs?", "/careers?", "search-results", "/job-list"]
    for pattern in bad_url_patterns:
        if pattern in u:
            return False
    try:
        job_list_indicators = [".job-listing", ".job-card", ".jobsList",
                               "[class*='search-result']", "[class*='job-list']"]
        for sel in job_list_indicators:
            if len(page.query_selector_all(sel)) > 3:
                return False
    except Exception:
        pass
    try:
        if not page.query_selector("form, input[type='email'], input[type='text'], input[type='file']"):
            return False
    except Exception:
        pass
    return True


# ── Low-level form helpers ────────────────────────────────────────────────────

def _fill(page, selectors: list, value: str) -> bool:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def _select_dropdown(page, selectors: list, value: str) -> bool:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.select_option(label=value)
                return True
        except Exception:
            try:
                el = page.query_selector(sel)
                if el:
                    el.select_option(value=value)
                    return True
            except Exception:
                continue
    return False


def _upload(page, selectors: list, path: str) -> bool:
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.set_input_files(path)
                return True
        except Exception:
            continue
    try:
        for inp in page.query_selector_all("input[type='file']"):
            try:
                inp.set_input_files(path)
                return True
            except Exception:
                continue
    except Exception:
        pass
    try:
        for drop_sel in ["[class*='dropzone']", "[class*='upload-area']",
                         "label[for*='resume']", "label[for*='cv']",
                         "button:has-text('Upload')", "button:has-text('Choose file')"]:
            el = page.query_selector(drop_sel)
            if el and el.is_visible():
                with page.expect_file_chooser() as fc_info:
                    el.click()
                fc_info.value.set_files(path)
                return True
    except Exception:
        pass
    return False


def _click_submit(page) -> bool:
    for sel in ["button[type='submit']", "input[type='submit']",
                "button:has-text('Submit')", "button:has-text('Apply')",
                "button:has-text('Send application')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


# ── ATS form fillers ──────────────────────────────────────────────────────────

def apply_greenhouse(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    _fill(page, ["#first_name", "input[name='first_name']", "input[placeholder*='First' i]"], first)
    _fill(page, ["#last_name",  "input[name='last_name']",  "input[placeholder*='Last' i]"],  last)
    _fill(page, ["#email", "input[name='email']", "input[type='email']",
                 "input[placeholder*='Email' i]"],                                            profile["email"])
    _fill(page, ["#phone", "input[name='phone']", "input[type='tel']",
                 "input[placeholder*='Phone' i]"],                                            profile["phone"])
    _fill(page, ["input[name='location']", "input[placeholder*='Location' i]",
                 "input[placeholder*='City' i]", "#location"],
          profile.get("current_city", "Delhi, India"))

    if profile.get("linkedin_url"):
        _fill(page, ["#linkedin_url", "input[name='linkedin_profile']",
                     "input[placeholder*='LinkedIn' i]"], profile["linkedin_url"])

    notice = profile.get("notice_period", "30 days")
    if not _select_dropdown(page, ["select[name*='notice' i]", "select[id*='notice' i]"], notice):
        _fill(page, ["input[name*='notice' i]", "input[placeholder*='notice' i]"], notice)

    uploaded = False
    try:
        for inp in page.query_selector_all("input[type='file']"):
            try:
                inp.set_input_files(profile["resume_path"])
                uploaded = True
                break
            except Exception:
                continue
    except Exception:
        pass

    if not uploaded:
        for sel in ["button:has-text('Attach')", "a:has-text('Attach')", "[class*='attach']"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        btn.click()
                    fc_info.value.set_files(profile["resume_path"])
                    uploaded = True
                    break
            except Exception:
                continue

    time.sleep(2)
    return _click_submit(page)


def apply_lever(page, profile: dict) -> bool:
    time.sleep(2)
    _fill(page, ["input[name='name']",  "#name",  "input[placeholder*='name' i]"], profile["full_name"])
    _fill(page, ["input[name='email']", "#email", "input[type='email']"],           profile["email"])
    _fill(page, ["input[name='phone']", "#phone", "input[type='tel']"],             profile["phone"])
    _fill(page, ["input[name='org']", "input[placeholder*='company' i]"],           profile.get("current_company", ""))
    if profile.get("linkedin_url"):
        _fill(page, ["input[name='urls[LinkedIn]']", "input[placeholder*='LinkedIn' i]"], profile["linkedin_url"])
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def apply_workday(page, profile: dict) -> bool:
    time.sleep(3)
    name_parts = profile["full_name"].split(" ", 1)
    _fill(page, ["input[data-automation-id='legalNameSection_firstName']",
                 "input[placeholder*='First' i]"], name_parts[0])
    _fill(page, ["input[data-automation-id='legalNameSection_lastName']",
                 "input[placeholder*='Last' i]"],  name_parts[1] if len(name_parts) > 1 else "")
    _fill(page, ["input[data-automation-id='email']",  "input[type='email']"], profile["email"])
    _fill(page, ["input[data-automation-id='phone']",  "input[type='tel']"],   profile["phone"])
    _upload(page, ["input[type='file']", "input[data-automation-id='file-upload-input-ref']"],
            profile["resume_path"])
    time.sleep(1)
    for sel in ["button[data-automation-id='bottom-navigation-next-button']",
                "button:has-text('Next')", "button:has-text('Apply')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def apply_smartrecruiters(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    for sel in ["button[data-ui='apply-btn']", "a[data-ui='apply-btn']",
                "button:has-text('Apply')", "a:has-text('Apply now')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                break
        except Exception:
            continue

    try:
        page.wait_for_selector("input[name='firstName'], input[type='email']", timeout=8000)
    except Exception:
        time.sleep(3)

    _fill(page, ["input[name='firstName']",   "input[placeholder*='First' i]"],   first)
    _fill(page, ["input[name='lastName']",    "input[placeholder*='Last' i]"],    last)
    _fill(page, ["input[name='email']",       "input[type='email']"],             profile["email"])
    _fill(page, ["input[name='phoneNumber']", "input[type='tel']",
                 "input[placeholder*='Phone' i]"],                                profile["phone"])
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)

    for step in range(4):
        clicked = False
        for sel in ["button[data-ui='submit-btn']", "button[data-ui='next-btn']",
                    "button:has-text('Submit')", "button:has-text('Next')",
                    "button:has-text('Continue')", "button[type='submit']"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    time.sleep(2)
                    clicked = True
                    break
            except Exception:
                continue
        for success_sel in ["text=Application submitted", "text=Thank you",
                            "text=Successfully applied", "[class*='success']"]:
            try:
                if page.query_selector(success_sel):
                    return True
            except Exception:
                continue
        if not clicked:
            break
    return True


def apply_zoho(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    for sel in ["a:has-text('Apply')", "button:has-text('Apply')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except Exception:
            continue

    try:
        page.wait_for_selector("input[name='firstName'], input[type='email']", timeout=6000)
    except Exception:
        time.sleep(2)

    _fill(page, ["input[name='firstName']", "input[id*='firstName']",
                 "input[placeholder*='First' i]"],                         first)
    _fill(page, ["input[name='lastName']",  "input[id*='lastName']",
                 "input[placeholder*='Last' i]"],                          last)
    _fill(page, ["input[name='email']",     "input[type='email']",
                 "input[id*='email' i]"],                                  profile["email"])
    _fill(page, ["input[name='mobile']",    "input[name='phone']",
                 "input[type='tel']"],                                     profile["phone"])
    _fill(page, ["input[name='currentEmployer']",
                 "input[placeholder*='current company' i]"],               profile.get("current_company", ""))
    _fill(page, ["input[name='currentJobTitle']",
                 "input[placeholder*='designation' i]"],                   profile.get("current_job_title", ""))
    _upload(page, ["input[type='file']", "input[name='resume']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def apply_keka(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    _fill(page, ["input[name='firstName']", "input[placeholder*='First' i]"], name_parts[0])
    _fill(page, ["input[name='lastName']",  "input[placeholder*='Last' i]"],
          name_parts[1] if len(name_parts) > 1 else "")
    _fill(page, ["input[name='email']",   "input[type='email']"],  profile["email"])
    _fill(page, ["input[name='phone']",   "input[type='tel']"],    profile["phone"])
    _fill(page, ["input[name='currentOrganization']",
                 "input[placeholder*='current company' i]"],        profile.get("current_company", ""))
    _fill(page, ["input[name='noticePeriod']",
                 "input[placeholder*='notice' i]"],                 profile.get("notice_period", "30 days"))
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def apply_darwinbox(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    _fill(page, ["input[name='first_name']", "input[placeholder*='First' i]"], name_parts[0])
    _fill(page, ["input[name='last_name']",  "input[placeholder*='Last' i]"],
          name_parts[1] if len(name_parts) > 1 else "")
    _fill(page, ["input[name='email']", "input[type='email']"], profile["email"])
    _fill(page, ["input[name='phone']", "input[type='tel']"],   profile["phone"])
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def apply_bamboohr(page, profile: dict) -> bool:
    time.sleep(2)
    _fill(page, ["#first_name", "input[name='first_name']"], profile["full_name"].split()[0])
    _fill(page, ["#last_name",  "input[name='last_name']"],  " ".join(profile["full_name"].split()[1:]))
    _fill(page, ["#email",  "input[name='email']",  "input[type='email']"], profile["email"])
    _fill(page, ["#phone",  "input[name='phone']",  "input[type='tel']"],   profile["phone"])
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def apply_generic(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    filled_first = _fill(page, ["input[name='first_name']", "input[name='firstName']",
                                 "input[placeholder='First Name']", "input[id*='first' i]"], first)
    filled_last  = _fill(page, ["input[name='last_name']",  "input[name='lastName']",
                                 "input[placeholder='Last Name']",  "input[id*='last' i]"],  last)

    if not filled_first and not filled_last:
        _fill(page, ["input[name='name']", "input[placeholder='Full Name']",
                     "input[placeholder*='Your name' i]"], profile["full_name"])

    _fill(page, ["input[type='email']", "input[name='email']",
                 "input[id*='email' i]", "input[placeholder*='email' i]"], profile["email"])

    _fill(page, ["input[type='tel']", "input[name='phone']", "input[name='mobile']",
                 "input[id*='phone' i]", "input[placeholder*='phone' i]"], profile["phone"])

    if profile.get("linkedin_url"):
        _fill(page, ["input[placeholder*='linkedin' i]", "input[name*='linkedin' i]"],
              profile["linkedin_url"])

    bio = (
        f"I am {profile['full_name']}, currently working as "
        f"{profile.get('current_job_title', 'a Data Scientist')} "
        f"with {profile.get('years_of_experience', '1')} years of experience. "
        f"Notice period: {profile.get('notice_period', '30 days')}."
    )
    for sel in ["textarea[name*='about' i]", "textarea[name*='cover' i]",
                "textarea[placeholder*='about' i]", "textarea[placeholder*='cover' i]",
                "textarea"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(bio)
                break
        except Exception:
            continue

    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)

    for sel in ["button[type='submit']", "input[type='submit']",
                "button:has-text('Submit')", "button:has-text('Apply')",
                "button:has-text('Send')", "button:has-text('Apply now')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click()
                time.sleep(3)
                return True
        except Exception:
            continue
    return False


def apply_oracle(page, profile: dict) -> bool:
    time.sleep(2)
    # Oracle HCM uses the candidate's own email/password for their portal account
    portal_email    = _email()
    portal_password = _password()

    _fill(page, ["input[type='email']", "input[placeholder*='email' i]",
                 "input[name*='email' i]"], portal_email)
    time.sleep(1)

    for sel in ["button[type='submit']", "button:has-text('Next')", "button[aria-label='Next']"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(3)
                break
        except Exception:
            continue

    password_appeared = False
    for sel in ["input[type='password']", "input[name*='password' i]"]:
        try:
            el = page.wait_for_selector(sel, timeout=5000)
            if el and el.is_visible():
                password_appeared = True
                _fill(page, [sel], portal_password)
                break
        except Exception:
            continue

    if not password_appeared:
        name_parts = profile["full_name"].split(" ", 1)
        _fill(page, ["input[name*='firstName' i]", "input[placeholder*='First' i]"], name_parts[0])
        _fill(page, ["input[name*='lastName' i]",  "input[placeholder*='Last' i]"],
              name_parts[1] if len(name_parts) > 1 else "")
        _fill(page, ["input[type='password']", "input[name*='password' i]"], portal_password)
        _fill(page, ["input[name*='confirm' i]", "input[placeholder*='confirm' i]"], portal_password)

    _click_submit(page)
    time.sleep(3)
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)

    for step in range(5):
        for sel in ["button[title='Next']", "button:has-text('Next')",
                    "button:has-text('Continue')", "button:has-text('Submit')",
                    "button[data-automation-id='bottom-navigation-next-button']"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    time.sleep(2)
                    break
            except Exception:
                continue
        for success_sel in ["text=Application submitted", "text=Thank you for applying",
                            "text=Successfully submitted"]:
            try:
                if page.query_selector(success_sel):
                    return True
            except Exception:
                continue
    return True


def apply_skillindia(page, profile: dict) -> bool:
    time.sleep(2)
    portal_email    = _email()
    portal_password = _password()

    for sel in ["a:has-text('Login')", "button:has-text('Login')",
                "a:has-text('Login/Register')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except Exception:
            continue

    email_filled = _fill(page, ["input[type='email']", "input[name='email']",
                                 "input[placeholder*='email' i]"], portal_email)

    if email_filled:
        _fill(page, ["input[type='password']", "input[name='password']"], portal_password)
        _click_submit(page)
        time.sleep(3)

        if "login" in page.url.lower() or "signin" in page.url.lower():
            for sel in ["a:has-text('Register')", "button:has-text('Register')"]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(2)
                        break
                except Exception:
                    continue

            name_parts = profile["full_name"].split(" ", 1)
            _fill(page, ["input[name='firstName']", "input[placeholder*='First' i]"], name_parts[0])
            _fill(page, ["input[name='lastName']",  "input[placeholder*='Last' i]"],
                  name_parts[1] if len(name_parts) > 1 else "")
            _fill(page, ["input[type='email']", "input[name='email']"], portal_email)
            _fill(page, ["input[type='password']", "input[name='password']"], portal_password)
            _fill(page, ["input[name='phone']", "input[type='tel']"], profile["phone"])
            _click_submit(page)
            time.sleep(3)

    for sel in ["button:has-text('Apply for This Opportunity')", "button:has-text('Apply')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def apply_trakstar(page, profile: dict) -> bool:
    time.sleep(2)
    for sel in ["button:has-text('Apply')", "a:has-text('Apply')", "input[value='Apply']"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except Exception:
            continue

    try:
        page.wait_for_selector("input[type='text'], input[type='email']", timeout=6000)
    except Exception:
        time.sleep(2)

    name_parts = profile["full_name"].split(" ", 1)
    _fill(page, ["input[name='first_name']", "input[placeholder*='First' i]"], name_parts[0])
    _fill(page, ["input[name='last_name']",  "input[placeholder*='Last' i]"],
          name_parts[1] if len(name_parts) > 1 else "")
    _fill(page, ["input[type='email']",  "input[name='email']",  "input[placeholder*='email' i]"], profile["email"])
    _fill(page, ["input[type='tel']",    "input[name='phone']",  "input[placeholder*='phone' i]"], profile["phone"])
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


ATS_HANDLERS = {
    "greenhouse":      apply_greenhouse,
    "lever":           apply_lever,
    "workday":         apply_workday,
    "smartrecruiters": apply_smartrecruiters,
    "zoho":            apply_zoho,
    "keka":            apply_keka,
    "darwinbox":       apply_darwinbox,
    "bamboohr":        apply_bamboohr,
    "oracle":          apply_oracle,
    "skillindia":      apply_skillindia,
    "trakstar":        apply_trakstar,
    "unknown":         apply_generic,
}


# ── External apply orchestrator ───────────────────────────────────────────────

def apply_external(job_page, context, profile: dict) -> str:
    external_btn = None
    for sel in ["a:has-text('Apply on Company Site')",
                "a:has-text('Apply on company website')",
                "button:has-text('Apply on Company Site')",
                "a[target='_blank']:has-text('Apply')"]:
        try:
            el = job_page.query_selector(sel)
            if el and el.is_visible():
                external_btn = el
                break
        except Exception:
            continue

    if not external_btn:
        return "skipped"

    with context.expect_page() as new_page_info:
        external_btn.click()
    ext_page = new_page_info.value
    ext_page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    accept_cookies(ext_page)

    if not is_valid_apply_page(ext_page, ext_page.url):
        ext_page.close()
        return "skipped"

    ats = detect_ats(ext_page.url)
    _log(f"External ATS detected: {ats} — {ext_page.url[:60]}", "info")
    _screenshot(ext_page)

    handler = ATS_HANDLERS.get(ats, apply_generic)
    try:
        success = handler(ext_page, profile)
        _screenshot(ext_page)
        ext_page.close()
        return "applied" if success else "skipped"
    except Exception as e:
        _log(f"External ATS error: {e}", "warning")
        try:
            ext_page.close()
        except Exception:
            pass
        return "skipped"


# ── Naukri login ──────────────────────────────────────────────────────────────

def _is_logged_in(page) -> bool:
    """Return True if the current Naukri page has an active session."""
    # Fastest check: if "Login to apply" is absent AND apply button is present,
    # or if the nav has a profile/user link, we're logged in.
    try:
        login_btn = page.query_selector("#login-apply-button")
        if login_btn and login_btn.is_visible():
            return False
    except Exception:
        pass
    for sel in [
        "a[href*='/mnjuser/homepage']",
        "a[href*='/mnjuser/profile']",
        ".nI-gNb-drawer__icon",          # hamburger menu only shown when logged in
        "span[class*='nI-gNb-menu']",
        "div[class*='user-name']",
        ".view-profile-wrapper",
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                return True
        except Exception:
            continue
    return False


def login_naukri(page) -> str:
    """
    Log in to Naukri.  Uses the real field IDs found via DOM inspection.
    Handles the case where a persistent browser profile already has a valid
    session — in that case Naukri redirects away from /nlogin immediately.
    Returns 'success' | 'wrong_credentials' | 'failed'.
    """
    _log("Opening Naukri...", "info")
    try:
        page.goto("https://www.naukri.com/nlogin/login",
                  wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        _log(f"Naukri login page failed to load: {exc}", "error")
        return "failed"

    # If the persistent profile already has a valid session, Naukri redirects
    # away from /nlogin before the form fields are rendered. Detect this early.
    url = page.url.lower()
    if "nlogin" not in url and "login" not in url and "naukri.com" in url:
        _log("Naukri session active (already logged in).", "success")
        return "success"

    # Wait for the email field — real ID confirmed via live DOM inspection
    try:
        page.wait_for_selector("#usernameField", timeout=8_000)
    except Exception:
        # If still not found, check URL one more time
        url = page.url.lower()
        if "nlogin" not in url and "login" not in url and "naukri.com" in url:
            _log("Naukri session active (redirected after wait).", "success")
            return "success"

    # Check once more — might have redirected during the wait
    url = page.url.lower()
    if "nlogin" not in url and "login" not in url and "naukri.com" in url:
        _log("Naukri session active.", "success")
        return "success"

    try:
        filled_email = _fill(page, [
            "#usernameField",
            "input[placeholder='Enter Email ID / Username']",
            "input[placeholder*='Email' i]",
        ], _email())
        filled_pwd = _fill(page, [
            "#passwordField",
            "input[placeholder='Enter Password']",
            "input[type='password']",
        ], _password())

        if not filled_email or not filled_pwd:
            _log("Could not locate login form fields.", "error")
            return "failed"

        # Confirmed class from live DOM inspection
        page.click("button.blue-btn[type='submit']")
    except Exception as exc:
        _log(f"Could not fill login form: {exc}", "error")
        return "failed"

    # Wait for the redirect away from /nlogin
    try:
        page.wait_for_function(
            "() => !window.location.href.includes('/nlogin')",
            timeout=12_000,
        )
    except Exception:
        pass

    time.sleep(0.5)
    _screenshot(page)

    # Inline wrong-credentials errors
    for err_text in ["Invalid credentials", "Enter correct", "Incorrect password",
                     "user does not exist", "Please enter valid"]:
        try:
            el = page.query_selector(f"text={err_text}")
            if el and el.is_visible():
                _log("Wrong Naukri credentials.", "error")
                return "wrong_credentials"
        except Exception:
            continue

    url = page.url.lower()
    if "nlogin" not in url and "login" not in url and "naukri.com" in url:
        _log("Naukri login successful.", "success")
        return "success"

    _log("Naukri login could not be verified — check credentials.", "error")
    return "wrong_credentials"


# ── Naukri chatbot / questionnaire handler ────────────────────────────────────

def _llm_pick_option(question: str, options: list[str], profile: dict) -> int:
    """
    Ask GPT-4o-mini to pick the best radio option.
    Returns 0-based index. Falls back to heuristics when the API is unavailable.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    notice = str(profile.get("notice_period", "30")).replace("days", "").strip()

    if api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            opts_numbered = "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
            prompt = (
                "You are filling a job application questionnaire on behalf of a candidate.\n\n"
                f"Candidate profile:\n"
                f"- Name: {profile.get('full_name', '')}\n"
                f"- Role: {profile.get('current_job_title', 'Data Scientist')}\n"
                f"- Experience: {profile.get('years_of_experience', '1')} years\n"
                f"- Notice period: {notice} days\n"
                f"- Current salary: {profile.get('current_salary', '300000')}\n"
                f"- Expected salary: {profile.get('expected_salary', '700000')}\n"
                f"- Location: {profile.get('current_city', 'Delhi')}\n\n"
                f"Question: {question}\n\nOptions:\n{opts_numbered}\n\n"
                "For relocation/location questions, always answer 'Yes' — the candidate is open to relocating.\n"
                "Reply with ONLY the option number (e.g. '2'). Nothing else."
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            m = re.search(r"\d+", raw)
            if m:
                idx = int(m.group()) - 1
                if 0 <= idx < len(options):
                    _log(f"GPT chose option {idx + 1}: {options[idx]!r}", "info")
                    return idx
        except Exception as exc:
            _log(f"LLM option picker failed ({exc!r}), using heuristic.", "warning")

    # ── Heuristic fallback ────────────────────────────────────────────────────
    notice_days = int(notice) if notice.isdigit() else 30
    q = question.lower()

    for i, opt in enumerate(options):
        o = opt.lower()
        if "skip" in o:
            continue
        if any(w in q for w in ["notice", "joining", "available", "when can"]):
            if notice_days <= 15 and "15" in o:       return i
            if notice_days <= 30 and "1 month" in o:  return i
            if notice_days <= 60 and "2 month" in o:  return i
            if notice_days <= 90 and "3 month" in o:  return i
        if any(w in q for w in ["relocat", "residing", "location", "city", "work from"]):
            if o in ("yes", "y"):                      return i
        if any(w in q for w in ["experience", "year"]):
            years = str(profile.get("years_of_experience", "1"))
            if years in o:
                return i

    for i, opt in enumerate(options):
        if "skip" not in opt.lower():
            return i
    return 0


def _get_radio_options(page) -> list[tuple[str, object]]:
    """
    Return list of (label_text, clickable_element) for all visible radio options.
    Always returns the LABEL or CONTAINER as the click target — never the hidden
    <input> itself, because Naukri styles its radio inputs as display:none.
    """
    options: list[tuple[str, object]] = []

    # Method 1: .ssrc__radio-btn-container (old inline chatbot)
    try:
        containers = page.query_selector_all(".ssrc__radio-btn-container")
        for c in containers:
            if not c.is_visible():
                continue
            label_text = ""
            click_target = c  # default: click the container itself
            # prefer the <label> child as the click target
            for lbl_sel in ["label", "[class*='label']", "span", "p"]:
                try:
                    lbl = c.query_selector(lbl_sel)
                    if lbl and lbl.is_visible():
                        t = lbl.inner_text().strip()
                        if t:
                            label_text = t
                            click_target = lbl
                            break
                except Exception:
                    pass
            if not label_text:
                label_text = c.inner_text().strip()
            if label_text:
                options.append((label_text, click_target))
    except Exception:
        pass

    if options:
        return options

    # Method 2: <label> elements that contain or are associated with a radio input
    try:
        for lbl in page.query_selector_all("label"):
            if not lbl.is_visible():
                continue
            # Check it's associated with a radio
            has_radio = False
            try:
                has_radio = bool(lbl.query_selector("input[type='radio']"))
            except Exception:
                pass
            if not has_radio:
                try:
                    for_id = lbl.get_attribute("for") or ""
                    if for_id:
                        inp = page.query_selector(f"#{for_id}")
                        if inp and inp.get_attribute("type") == "radio":
                            has_radio = True
                except Exception:
                    pass
            if not has_radio:
                continue
            label_text = lbl.inner_text().strip()
            if label_text and len(label_text) < 120:
                options.append((label_text, lbl))  # click the label, not the hidden input
    except Exception:
        pass

    return options


def _chatbot_save(page) -> bool:
    """
    Click the chatbot's Save/Submit button.
    Uses exact-text matching for div/span to avoid clicking ancestor containers.
    Returns True if a button was successfully clicked.
    """
    # ── Exact-text helpers ────────────────────────────────────────────────────
    def _exact_text_click(tags: list[str], texts: list[str]) -> bool:
        for tag in tags:
            for el in page.query_selector_all(tag):
                try:
                    if not el.is_visible():
                        continue
                    if el.inner_text().strip() in texts:
                        el.click()
                        time.sleep(0.5)
                        return True
                except Exception:
                    continue
        return False

    # 1. Standard <button> — :has-text is fine here (buttons are leaf-ish)
    for sel in [
        "button:has-text('Save')",
        "button:has-text('Done')",
        "button:has-text('Submit')",
        "button:has-text('Proceed')",
        "button:has-text('Next')",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(0.5)
                return True
        except Exception:
            continue

    # 2. <div>/<span> styled as button — exact text only (avoid matching ancestors)
    if _exact_text_click(["div", "span", "a"],
                         ["Save", "Done", "Submit", "Proceed", "Next"]):
        return True

    # 3. Class-based
    for sel in [
        "[class*='save-btn']", "[class*='saveBtn']",
        "[class*='submit-btn']", "[class*='done-btn']",
        "[class*='ssrc__save']", "[class*='chatbot-save']",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(0.5)
                return True
        except Exception:
            continue

    # 4. Force-click on <button> as last resort
    for sel in ["button:has-text('Save')", "button:has-text('Submit')"]:
        try:
            btn = page.query_selector(sel)
            if btn:
                btn.click(force=True)
                time.sleep(0.5)
                return True
        except Exception:
            continue

    return False


def _chatbot_answer(question: str, profile: dict) -> str:
    """Return a sensible text answer for a Naukri chatbot question."""
    q = question.lower()
    if any(w in q for w in ["notice", "joining", "available"]):
        return profile.get("notice_period", "30").replace("days", "").strip()
    if any(w in q for w in ["experience", "year", "exp"]):
        return profile.get("years_of_experience", "1")
    if any(w in q for w in ["salary", "ctc", "package", "compensation"]):
        return profile.get("expected_salary", "700000")
    if any(w in q for w in ["location", "city", "relocat"]):
        return profile.get("current_city", "Delhi")
    if any(w in q for w in ["phone", "mobile", "contact"]):
        return profile.get("phone", "")
    return "1"   # safe numeric fallback for anything else


def _handle_naukri_chatbot(page, profile: dict) -> bool:
    """
    Handle Naukri's post-Apply chatbot questionnaire (both old inline style
    and the newer modal/dialog style).
    Returns True if a chatbot was detected (regardless of completion).
    """
    # ── Detect chatbot / questionnaire presence ───────────────────────────────
    chatbot_detected = False
    for sel in [
        "ul[id*='chatList_']",
        ".ssrc__radio-btn-container",
        "li[class*='botItem']",
        "[class*='chatbot']",
        ".textArea",
        "[class*='questionnaire']",
        "[class*='apply-questionnaire']",
    ]:
        try:
            if page.query_selector(sel):
                chatbot_detected = True
                break
        except Exception:
            continue

    # Also trigger on any visible radio button (covers newer modal layouts)
    if not chatbot_detected:
        try:
            for r in page.query_selector_all("input[type='radio']"):
                if r.is_visible():
                    chatbot_detected = True
                    break
        except Exception:
            pass

    if not chatbot_detected:
        return False

    _log("Chatbot questionnaire detected — answering...", "info")

    for _round in range(20):
        time.sleep(0.5)
        _screenshot(page)

        # ── Extract current question text ──────────────────────────────────
        question_text = ""
        for q_sel in [
            "xpath=//li[contains(@class,'botItem')]//span",
            "[class*='ssrc__question']",
            "[class*='question-text']",
            "[class*='chatbot'] p",
            "[class*='questionnaire'] p",
            "dialog p",
            "[role='dialog'] p",
        ]:
            try:
                els = page.query_selector_all(q_sel)
                for el in reversed(els):
                    if el.is_visible():
                        t = el.inner_text().strip()
                        if t and len(t) > 5:
                            question_text = t
                            break
            except Exception:
                continue
            if question_text:
                break

        # ── Radio-button options ───────────────────────────────────────────
        options = _get_radio_options(page)

        if options:
            labels = [o[0] for o in options]
            _log(f"Q: {question_text!r} | Options: {labels}", "info")
            best_idx = _llm_pick_option(question_text, labels, profile)
            _, target = options[best_idx]
            # Click label/container (never hidden input — Naukri hides radio inputs)
            try:
                target.click()
            except Exception:
                try:
                    target.click(force=True)
                except Exception:
                    pass
            time.sleep(0.3)
            saved = _chatbot_save(page)
            if not saved:
                _log("Save button not found — trying force-click on any save-like element.", "warning")
            time.sleep(0.3)
            # If the same options are still visible, save didn't work — break to avoid infinite loop
            still_stuck = bool(_get_radio_options(page))
            if still_stuck and saved:
                # Options still present means a new question appeared — loop will handle it
                pass
            elif still_stuck and not saved:
                _log("Could not save chatbot answer — skipping questionnaire.", "warning")
                break
            continue

        # ── Text-input question ────────────────────────────────────────────
        text_input = None
        for sel in [".textArea", "textarea", "input[class*='textArea']",
                    "input[type='text']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    text_input = el
                    break
            except Exception:
                continue

        if text_input:
            answer = _chatbot_answer(question_text, profile)
            try:
                text_input.fill(answer)
                time.sleep(0.2)
                _chatbot_save(page)
            except Exception:
                pass
            continue

        # ── No interactive element — chatbot is done or truly stuck ───────
        if not _chatbot_save(page):
            break

    return True


# ── Job search ────────────────────────────────────────────────────────────────

def get_job_links(page, needed: int) -> list[str]:
    query = _search_query()
    loc   = _location()
    _log(f"Searching for '{query}' jobs in {loc}...", "info")

    slug = query.lower().replace(' ', '-')
    loc_slug = loc.lower().replace(' ', '-')
    search_url = (
        f"https://www.naukri.com/{slug}-jobs-in-{loc_slug}"
        f"?k={query.replace(' ', '%20')}&l={loc.replace(' ', '%20')}&nignbevent_src=jobsearchDeskGNB"
    )
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        _log(f"Job search page failed: {exc}", "warning")
        return []

    # Wait for JS-rendered job cards before scraping
    for wait_sel in [
        "div[class*='srp-jobtuple']",
        "article[class*='jobTuple']",
        "div[class*='job-tuple']",
        ".cust-job-tuple",
    ]:
        try:
            page.wait_for_selector(wait_sel, timeout=8_000)
            break
        except Exception:
            continue
    else:
        time.sleep(5)   # last-resort wait if no known selector appeared

    _screenshot(page)

    # Try selectors from newest to oldest Naukri DOM versions
    link_selectors = [
        "a[class*='title'][href*='naukri.com']",
        "a.title[href*='naukri.com']",
        "div[class*='srp-jobtuple'] a[href*='naukri.com']",
        "article[class*='jobTuple'] a[href*='naukri.com']",
        "div[class*='job-tuple'] a[href*='naukri.com']",
        ".cust-job-tuple a.title",
        ".jobTitle a",
        "a.job-title",
    ]

    links = []
    for sel in link_selectors:
        try:
            elements = page.query_selector_all(sel)
            if not elements:
                continue
            for el in elements:
                href = el.get_attribute("href") or ""
                # Naukri job detail URLs contain "-JD-" or end in a numeric ID
                if "naukri.com" in href and ("-JD-" in href or href.rstrip("/").split("-")[-1].isdigit()):
                    links.append(href)
            if links:
                break
        except Exception:
            continue

    # Fallback: grab every naukri.com link and filter by job-URL pattern
    if not links:
        try:
            for el in page.query_selector_all("a[href*='naukri.com']"):
                href = el.get_attribute("href") or ""
                if ("-JD-" in href or href.rstrip("/").split("-")[-1].isdigit()) \
                        and "/jobs/" not in href and "search" not in href:
                    links.append(href)
        except Exception:
            pass

    seen, unique = set(), []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    _log(f"Found {len(unique)} job listings.", "found")
    return unique[:needed]


# ── Applied-URL cache (cross-run deduplication) ───────────────────────────────

def _applied_urls_path(profile: dict) -> Path:
    return Path(profile.get("resume_path", "")).parent / "naukri_applied_urls.json"

def _load_applied_urls(profile: dict) -> set:
    try:
        p = _applied_urls_path(profile)
        if p.exists():
            return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return set()

def _save_applied_url(profile: dict, url: str) -> None:
    try:
        p = _applied_urls_path(profile)
        urls = _load_applied_urls(profile)
        urls.add(url)
        p.write_text(json.dumps(list(urls)), encoding="utf-8")
    except Exception:
        pass


# ── Per-job apply ─────────────────────────────────────────────────────────────

def try_apply_to_job(page, context, job_url: str, index: int,
                     profile: dict, stop_event,
                     applied_urls: set | None = None) -> str:
    if stop_event is not None and stop_event.is_set():
        return "skipped"

    # Cross-run deduplication — skip URLs already processed in a previous run
    if applied_urls is not None and job_url in applied_urls:
        _log(f"[{index}] Already processed in a previous run — skipping.", "info")
        _send_company(index, "Unknown", "Unknown", "", "already_applied",
                      "Previously applied (URL cache)", job_url)
        return "already_applied"

    job_page = context.new_page()
    title, company, location = "Unknown", "Unknown", ""
    try:
        job_page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
        # Wait for the apply button or already-applied marker — fires as soon as DOM is ready
        try:
            job_page.wait_for_selector(
                "#apply-button, button.apply-button, #already-applied, #login-apply-button",
                timeout=3000,
            )
        except Exception:
            pass

        for sel in ["h1.jd-header-title", ".jd-header-title", "h1[class*='title']", "h1"]:
            try:
                el = job_page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if t:
                        title = t
                        break
            except Exception:
                continue

        for sel in [".jd-header-comp-name a", ".jd-header-comp-name",
                    "[class*='comp-name'] a", "[class*='companyName']"]:
            try:
                el = job_page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if t:
                        company = t
                        break
            except Exception:
                continue

        for sel in [".location-text", "[class*='location']", ".loc"]:
            try:
                el = job_page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if t:
                        location = t
                        break
            except Exception:
                continue

        _log(f"[{index}] {title} @ {company}", "info")
        _screenshot(job_page)

        # If session expired on this job page, re-login before proceeding
        if not _is_logged_in(job_page):
            _log(f"[{index}] Session expired — re-logging in...", "warning")
            login_status = login_naukri(job_page)
            if login_status != "success":
                _log(f"[{index}] Re-login failed — skipping job.", "error")
                _send_company(index, title, company, location, "skipped",
                              "Session expired, re-login failed", job_url)
                return "skipped"
            # Navigate back to the job page after re-login
            job_page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(0.5)
            _screenshot(job_page)

        # ── Already applied? ──────────────────────────────────────────────────
        # Use the definitive DOM ID confirmed via live inspection.
        already_applied = False
        try:
            el = job_page.query_selector("#already-applied")
            if el and el.is_visible():
                already_applied = True
        except Exception:
            pass

        if not already_applied:
            for sel in [
                "[class*='styles_alert-message-text']",
                "div[class*='already-applied']",
            ]:
                try:
                    el = job_page.query_selector(sel)
                    if el and el.is_visible():
                        already_applied = True
                        break
                except Exception:
                    continue

        if already_applied:
            _log(f"[{index}] Already applied — skipping.", "info")
            _send_company(index, title, company, location, "already_applied",
                          "Already applied", job_url)
            return "already_applied"

        # ── Check if job requires login (session lost on this page) ───────
        try:
            login_btn = job_page.query_selector("#login-apply-button")
            if login_btn and login_btn.is_visible():
                _log(f"[{index}] Session expired — re-logging in...", "warning")
                login_status = login_naukri(job_page)
                if login_status != "success":
                    _send_company(index, title, company, location, "skipped",
                                  "Session expired, re-login failed", job_url)
                    return "skipped"
                job_page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(0.5)
                _screenshot(job_page)
        except Exception:
            pass

        # ── Find the Apply button (confirmed ID from DOM inspection) ───────
        easy_apply_btn = None
        for sel in [
            "#apply-button",                  # confirmed real ID
            "button.apply-button",            # confirmed real class
            "button[class*='apply-button']",
            "button[class*='ia-apply']",
        ]:
            try:
                btn = job_page.query_selector(sel)
                if btn and btn.is_visible():
                    txt = btn.inner_text().strip().lower()
                    if "login" not in txt and "register" not in txt:
                        easy_apply_btn = btn
                        break
            except Exception:
                continue

        # Fallback: any visible button with exact text "Apply"
        if not easy_apply_btn:
            try:
                for btn in job_page.query_selector_all("button"):
                    if btn.inner_text().strip().lower() == "apply" and btn.is_visible():
                        easy_apply_btn = btn
                        break
            except Exception:
                pass

        if easy_apply_btn:
            _log(f"[{index}] Clicking Apply...", "info")
            easy_apply_btn.click()
            # Wait for chatbot OR success confirmation — whichever comes first
            try:
                job_page.wait_for_selector(
                    "ul[id*='chatList_'], .ssrc__radio-btn-container, input[type='radio'], "
                    "span[class*='apply-message'], #apply-status-header, "
                    "#already-applied, [class*='apply-status']",
                    timeout=4000,
                )
            except Exception:
                pass
            _screenshot(job_page)

            # ── Handle Naukri chatbot questionnaire if it appeared ─────────
            _handle_naukri_chatbot(job_page, profile)
            time.sleep(0.3)
            _screenshot(job_page)

            # ── Success detection ──────────────────────────────────────────
            # 1. Official Naukri success selectors (confirmed from open-source bots)
            def _record_applied():
                if applied_urls is not None:
                    applied_urls.add(job_url)
                    _save_applied_url(profile, job_url)

            for sel in [
                "span[class*='apply-message']",
                "div[class*='apply-status-header'][class*='green']",
                "#apply-status-header",
            ]:
                try:
                    el = job_page.query_selector(sel)
                    if el and el.is_visible():
                        _log(f"[{index}] Applied via Naukri Easy Apply!", "success")
                        _send_company(index, title, company, location, "applied",
                                      "Naukri Easy Apply", job_url)
                        _record_applied()
                        return "applied"
                except Exception:
                    continue

            # 2. Success text phrases
            for phrase in ["successfully applied", "application submitted",
                           "you have applied", "applied successfully",
                           "thank you for applying",
                           "your application has been submitted"]:
                try:
                    el = job_page.query_selector(f"text={phrase}")
                    if el:
                        _log(f"[{index}] Applied via Naukri Easy Apply!", "success")
                        _send_company(index, title, company, location, "applied",
                                      "Naukri Easy Apply", job_url)
                        _record_applied()
                        return "applied"
                except Exception:
                    continue

            # 3. Button disabled / state changed to "Applied"
            try:
                re_btn = job_page.query_selector("#apply-button")
                if re_btn:
                    txt = re_btn.inner_text().strip().lower()
                    disabled = not re_btn.is_enabled()
                    if "applied" in txt or disabled:
                        _log(f"[{index}] Applied (button state changed).", "success")
                        _send_company(index, title, company, location, "applied",
                                      "Naukri Easy Apply", job_url)
                        _record_applied()
                        return "applied"
            except Exception:
                pass

            # 4. #already-applied now present means we just applied successfully
            try:
                el = job_page.query_selector("#already-applied")
                if el and el.is_visible():
                    _log(f"[{index}] Applied (confirmed by already-applied marker).", "success")
                    _send_company(index, title, company, location, "applied",
                                  "Naukri Easy Apply", job_url)
                    _record_applied()
                    return "applied"
            except Exception:
                pass

            _log(f"[{index}] Easy Apply clicked (could not confirm).", "warning")
            _send_company(index, title, company, location, "applied",
                          "Naukri Easy Apply (unconfirmed)", job_url)
            if applied_urls is not None:
                applied_urls.add(job_url)
                _save_applied_url(profile, job_url)
            return "applied"

        # ── No Naukri Easy Apply button — skip (external-only jobs ignored) ──
        _log(f"[{index}] No Easy Apply button — skipping (external site only).", "info")
        _send_company(index, title, company, location, "skipped",
                      "External site only", job_url)
        return "skipped"

    except Exception as e:
        _log(f"[{index}] Error: {e}", "warning")
        _send_company(index, title, company, location, "skipped", str(e), job_url)
        return "skipped"
    finally:
        try:
            job_page.close()
        except Exception:
            pass


# ── Public entry point ────────────────────────────────────────────────────────

def run_automation(
    profile: dict,
    logger=None,
    stop_event=None,
    email: str | None = None,
    password: str | None = None,
    search_query: str | None = None,
    location: str | None = None,
    max_apps: int | None = None,
    easy_apply: bool | None = None,   # accepted for API compatibility, Naukri always tries both
) -> None:
    """
    Run the full Naukri automation pipeline.
    Called by automation.py in a background daemon thread.
    All per-run config is stored in thread-local storage so concurrent runs
    for different users never overwrite each other.
    """
    # ── Store all per-run state in thread-local ────────────────────────────────
    _tls.logger       = logger
    _tls.email        = email        if email        is not None else NAUKRI_EMAIL
    _tls.password     = password     if password     is not None else NAUKRI_PASSWORD
    _tls.search_query = search_query if search_query is not None else JOB_SEARCH_QUERY
    _tls.location     = location     if location     is not None else JOB_LOCATION
    _tls.max_apps     = max_apps     if max_apps     is not None else MAX_APPLICATIONS

    if stop_event is not None and stop_event.is_set():
        return

    applied_count = 0

    with sync_playwright() as p:
        # Each Naukri account gets its own persistent browser profile so cookies
        # and session state are preserved between runs (mirrors LinkedIn pattern).
        email_slug   = hashlib.md5((_email() or "").strip().lower().encode()).hexdigest()[:12]
        profile_dir  = os.path.join(SCRIPT_DIR, f"naukri_browser_profile_{email_slug}")
        os.makedirs(profile_dir, exist_ok=True)

        from backend.config import BROWSER_HEADLESS
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=BROWSER_HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--window-size=1366,768",
                "--disable-infobars",
                "--disable-extensions",
                "--window-position=-10000,-10000",  # off-screen: bypasses CF, invisible to user
            ],
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        screencaster = CDPScreencaster(page, logger)
        screencaster.start()

        try:
            login_status = login_naukri(page)

            if login_status == "wrong_credentials":
                _log("Automation stopped: fix your Naukri credentials and try again.", "error")
                if logger:
                    logger.done()
                return

            if login_status == "failed":
                _log("Automation stopped: Naukri could not be reached.", "error")
                if logger:
                    logger.done()
                return

            job_links = get_job_links(page, needed=_max_apps())
            _log(f"Starting applications (target: {_max_apps()})...", "info")

            # Load applied URLs from previous runs for deduplication
            applied_urls = _load_applied_urls(profile)
            if applied_urls:
                _log(f"Loaded {len(applied_urls)} previously applied URLs — will skip them.", "info")

            for i, link in enumerate(job_links, start=1):
                if (stop_event is not None and stop_event.is_set()) or \
                   (logger is not None and hasattr(logger, "is_active") and not logger.is_active):
                    _log("Stop signal received — ending automation.", "warning")
                    break

                if page.is_closed():
                    _log("Browser page closed — opening fresh page.", "warning")
                    try:
                        page = context.new_page()
                        screencaster.stop()
                        screencaster = CDPScreencaster(page, logger)
                        screencaster.start()
                        login_status = login_naukri(page)
                        if login_status == "wrong_credentials":
                            _log("Re-login failed. Stopping.", "error")
                            break
                    except Exception as recovery_exc:
                        _log(f"Page recovery failed: {recovery_exc}", "error")
                        break

                status = try_apply_to_job(page, context, link, i, profile, stop_event,
                                          applied_urls=applied_urls)

                if status == "applied":
                    applied_count += 1
                    if logger:
                        logger.progress(applied_count, _max_apps())

                time.sleep(random.uniform(0.5, 1.5))

            summary = f"Done! {applied_count}/{_max_apps()} applications submitted."
            _log(summary, "success")
            if logger:
                logger.done(summary)

        except Exception as exc:
            _log(f"Fatal error: {exc}", "error")
            if logger:
                logger.fail(str(exc))

        finally:
            screencaster.stop()
            try:
                context.close()
            except Exception:
                pass
            _tls.logger = None


# ── Standalone script runner ──────────────────────────────────────────────────

def load_profile() -> dict:
    path = os.path.join(SCRIPT_DIR, "profile.json")
    if not os.path.exists(path):
        raise FileNotFoundError("profile.json not found. Run parse_resume.py first.")
    with open(path) as f:
        return json.load(f)


def main():
    profile = load_profile()
    print(f"Profile: {profile['full_name']} | {profile.get('current_job_title', '')}")
    run_automation(
        profile=profile,
        email=NAUKRI_EMAIL,
        password=NAUKRI_PASSWORD,
        search_query=JOB_SEARCH_QUERY,
        location=JOB_LOCATION,
        max_apps=MAX_APPLICATIONS,
    )


if __name__ == "__main__":
    main()
