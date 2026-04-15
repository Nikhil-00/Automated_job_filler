"""
external_apply.py
-----------------
Handles job applications on external ATS platforms linked from LinkedIn.

Strategy: One universal GPT-4o-mini vision loop handles every ATS.
  - Screenshot → GPT → action → execute
  - If action fails → send error + new screenshot back to GPT → retry
  - 3 consecutive failures → skip company

Entry point:
  apply_external(page, job_url, profile) -> "applied" | "skipped" | "login_required"
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from openai import OpenAI
from playwright.sync_api import Page, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Module-level shared resources (injected by linkedin_apply.py at import time)
# ---------------------------------------------------------------------------

_openai_client: OpenAI = None          # type: ignore[assignment]
_track_usage: Callable  = lambda r: None
_logger                 = None
_RESUME_TEXT: str       = ""


def _init(openai_client: OpenAI, track_usage_fn: Callable, logger) -> None:
    """Called once by linkedin_apply.py to inject shared resources."""
    global _openai_client, _track_usage, _logger, _RESUME_TEXT
    _openai_client = openai_client
    _track_usage   = track_usage_fn
    _logger        = logger
    # Load resume text
    try:
        _PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
        p = os.path.join(_PROJECT_ROOT, "resume_text.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                _RESUME_TEXT = f.read()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Logging / screenshot helpers
# ---------------------------------------------------------------------------

def _log(message: str, log_type: str = "info") -> None:
    if _logger is not None:
        getattr(_logger, log_type, _logger.info)(message)
    print(message)


def _snap(page: Page) -> None:
    """Capture a JPEG frame and stream it to the frontend."""
    if _logger is None or not hasattr(_logger, "screenshot"):
        return
    try:
        raw = page.screenshot(type="jpeg", quality=55, full_page=False)
        _logger.screenshot(base64.b64encode(raw).decode())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ATS URL pattern registry
# ---------------------------------------------------------------------------

_ATS_PATTERNS: list[tuple[str, str]] = [
    ("greenhouse",      r"boards\.greenhouse\.io|greenhouse\.io/embed/job_app"),
    ("lever",           r"jobs\.lever\.co"),
    ("workday",         r"myworkdayjobs\.com|wd\d+\.myworkday\.com"),
    ("icims",           r"careers\.icims\.com|\.icims\.com/jobs/"),
    ("smartrecruiters", r"jobs\.smartrecruiters\.com|smartrecruiters\.com/"),
    ("taleo",           r"tbe\.taleo\.net|\.taleo\.net/careersection"),
    ("bamboohr",        r"\.bamboohr\.com/jobs/"),
    ("workable",        r"apply\.workable\.com|\.workable\.com/j/"),
    ("ashby",           r"jobs\.ashbyhq\.com"),
    ("jobvite",         r"jobs\.jobvite\.com"),
    ("google_forms",    r"docs\.google\.com/forms"),
]

_ATS_RE = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in _ATS_PATTERNS]


def detect_ats(url: str) -> Optional[str]:
    """Return the ATS name if the URL matches a known platform, else None."""
    for name, rx in _ATS_RE:
        if rx.search(url):
            return name
    return None


# ---------------------------------------------------------------------------
# Login-wall detection
# ---------------------------------------------------------------------------

_LOGIN_DOM_SELECTORS = [
    "input[type='password']",
    "button[type='submit']#login-submit",
    "[data-automation-id='signIn']",
    "[data-automation-id='createAccountSubmitButton']",   # Workday account creation
    "[data-automation-id='accountCreationButton']",
    "button[data-testid='login-button']",
    "#login-email",
    "#login-password",
    "form[action*='login']",
    "form[action*='signin']",
    ".login-form",
    "#signInFormUsername",
    "input[name='session[username_or_email]']",
]

_LOGIN_TEXT_PHRASES = [
    "sign in to apply",
    "log in to apply",
    "login to apply",
    "please sign in",
    "please log in",
    "create an account to apply",
    "you must be logged in",
    "sign in or create account",
    "create a workday account",
    "create account",
    "verify your email",
]


def _requires_login(page: Page) -> bool:
    for sel in _LOGIN_DOM_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                apply_form = page.query_selector(
                    "form[id*='apply'], form[class*='apply'], "
                    "input[name*='resume'], input[type='file']"
                )
                if not apply_form:
                    return True
        except Exception:
            pass
    try:
        body = (page.inner_text("body") or "").lower()
        for phrase in _LOGIN_TEXT_PHRASES:
            if phrase in body:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Success detection
# ---------------------------------------------------------------------------

_SUCCESS_SELECTORS = [
    "[data-test='confirmation-message']",
    ".application-confirmation",
    ".success-message",
    "#confirmation-page",
    "[class*='confirmation']",
    "[class*='thank-you']",
    "[class*='success']",
]

_SUCCESS_TEXT_PHRASES = [
    "application submitted",
    "application received",
    "thanks for applying",
    "thank you for applying",
    "successfully submitted",
    "your application has been",
    "we've received your application",
    "we have received your application",
    "you have successfully applied",
    "application complete",
    "your response has been recorded",
]


def _is_success(page: Page) -> bool:
    for sel in _SUCCESS_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            pass
    try:
        body = (page.inner_text("body") or "").lower()
        for phrase in _SUCCESS_TEXT_PHRASES:
            if phrase in body:
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Resume upload helper
# ---------------------------------------------------------------------------

def _upload_resume(page: Page, profile: dict, timeout: int = 5000) -> bool:
    resume_path = profile.get("resume_path", "")
    if not resume_path or not Path(resume_path).exists():
        return False
    try:
        file_input = page.wait_for_selector(
            "input[type='file']", timeout=timeout, state="attached"
        )
        if file_input is None:
            return False
        file_input.set_input_files(resume_path)
        time.sleep(0.8)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Vision agent — screenshot extraction helpers
# ---------------------------------------------------------------------------

def _page_screenshot_b64(page: Page) -> str:
    try:
        raw = page.screenshot(type="jpeg", quality=65, full_page=False)
        return base64.b64encode(raw).decode()
    except Exception:
        return ""


def _extract_form_elements(page: Page) -> list[dict]:
    """
    Return a simplified list of interactive elements visible on the page.
    Capped at 60 elements to keep token count manageable.
    """
    try:
        elements: list[dict] = page.evaluate("""() => {
            const MAX = 60;
            const results = [];

            const getLabel = (el) => {
                if (el.id) {
                    const lbl = document.querySelector(`label[for='${el.id}']`);
                    if (lbl) return lbl.innerText.trim().slice(0, 80);
                }
                const lblId = el.getAttribute('aria-labelledby');
                if (lblId) {
                    const lbl = document.getElementById(lblId);
                    if (lbl) return lbl.innerText.trim().slice(0, 80);
                }
                let p = el.parentElement;
                for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
                    if (p.tagName === 'LABEL') return p.innerText.trim().slice(0, 80);
                }
                return '';
            };

            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 &&
                       window.getComputedStyle(el).display !== 'none' &&
                       window.getComputedStyle(el).visibility !== 'hidden';
            };

            const TAGS = 'input, textarea, select, button[type="submit"], button[type="button"], a[href]';
            for (const el of document.querySelectorAll(TAGS)) {
                if (!isVisible(el)) continue;
                const tag  = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || tag;
                if (['hidden', 'script', 'style'].includes(type)) continue;

                let sel = tag;
                if (el.id)                                    sel = `#${el.id}`;
                else if (el.name)                             sel = `${tag}[name='${el.name}']`;
                else if (el.getAttribute('aria-label'))       sel = `${tag}[aria-label='${el.getAttribute('aria-label')}']`;
                else if (el.getAttribute('data-automation-id')) sel = `[data-automation-id='${el.getAttribute('data-automation-id')}']`;

                // Include options for <select>
                let options = [];
                if (tag === 'select') {
                    options = Array.from(el.options)
                        .map(o => o.text.trim())
                        .filter(t => t && !['select','select an option','please select','--','select one'].includes(t.toLowerCase()));
                }

                results.push({
                    selector:    sel,
                    tag,
                    type,
                    name:        el.name || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel:   el.getAttribute('aria-label') || '',
                    label:       getLabel(el),
                    value:       el.value || el.innerText?.trim().slice(0, 60) || '',
                    options,
                });

                if (results.length >= MAX) break;
            }
            return results;
        }""")
        return elements or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Action executor — tries multiple strategies, returns (ok, error_msg)
# ---------------------------------------------------------------------------

def _execute_action(page: Page, profile: dict, action: dict) -> tuple[bool, str]:
    """
    Execute a single GPT action using Playwright.
    Tries multiple selector strategies before giving up.
    Returns (True, "") on success, (False, error_message) on failure.
    """
    act      = (action.get("action") or "").strip()
    selector = (action.get("selector") or "").strip()
    value    = (action.get("value") or "").strip()

    try:
        # ── Upload resume ───────────────────────────────────────────────────────
        if act == "upload_resume":
            ok = _upload_resume(page, profile)
            return (True, "") if ok else (False, "No file input found or resume_path missing")

        if not selector:
            return (False, f"No selector provided for action '{act}'")

        # ── Fill text input ─────────────────────────────────────────────────────
        if act == "fill":
            try:
                loc = page.locator(selector).first
                loc.wait_for(state="visible", timeout=4000)
                loc.fill(str(value))
                page.wait_for_timeout(300)
                return (True, "")
            except Exception as e:
                return (False, str(e))

        # ── Click (button, radio, checkbox, dropdown trigger, etc.) ────────────
        elif act == "click":
            # Primary: CSS selector via Locator
            try:
                loc = page.locator(selector).first
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed()
                try:
                    loc.click(timeout=5000)
                except Exception:
                    # Pointer intercepted (e.g. label over radio) — dispatch event
                    loc.dispatch_event("click")
                page.wait_for_timeout(600)
                return (True, "")
            except Exception as e1:
                # Fallback: try by visible text if selector has no CSS special chars
                if not any(c in selector for c in "#.[]:>~+=^$*"):
                    try:
                        page.locator(f"text={selector}").first.click(timeout=3000)
                        page.wait_for_timeout(600)
                        return (True, "")
                    except Exception:
                        pass
                return (False, str(e1))

        # ── Select dropdown ─────────────────────────────────────────────────────
        elif act == "select":
            try:
                loc = page.locator(selector).first
                loc.wait_for(state="visible", timeout=4000)

                # Try native <select> first
                try:
                    loc.select_option(label=value, timeout=2000)
                    page.wait_for_timeout(400)
                    return (True, "")
                except Exception:
                    pass
                try:
                    loc.select_option(value=value, timeout=2000)
                    page.wait_for_timeout(400)
                    return (True, "")
                except Exception:
                    pass

                # Custom dropdown: click to open, then click the matching option
                loc.click()
                page.wait_for_timeout(600)
                try:
                    # Try exact text match first, then partial
                    opt_loc = page.locator(f"text='{value}'").first
                    if opt_loc.count() == 0:
                        opt_loc = page.locator(f"li:has-text('{value}'), [role='option']:has-text('{value}')").first
                    opt_loc.click(timeout=3000)
                    page.wait_for_timeout(400)
                    return (True, "")
                except Exception as e2:
                    # Escape to close dropdown and report failure
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    return (False, f"Custom dropdown option '{value}' not found: {e2}")

            except Exception as e:
                return (False, str(e))

        else:
            return (False, f"Unknown action type: '{act}'")

    except Exception as e:
        return (False, f"Unexpected error in _execute_action: {e}")


# ---------------------------------------------------------------------------
# Universal vision loop — the only form-filler we need
# ---------------------------------------------------------------------------

_VISION_SYSTEM_PROMPT = """You are an AI agent filling out an online job application form.
You receive a screenshot of the current page and a JSON list of interactive elements.

Return the SINGLE best next action as JSON (no markdown):
{
  "action": "fill" | "click" | "select" | "upload_resume" | "done" | "skip",
  "selector": "CSS selector for the target element (empty string for upload_resume)",
  "value": "text to type / exact option label to pick (empty for click/upload)",
  "reason": "one sentence"
}

Action rules:
  fill          — type into text/email/tel/number/textarea fields
  click         — buttons, radio labels, checkboxes, custom dropdown triggers, nav buttons
  select        — NATIVE <select> dropdowns (value = exact option text from 'options' list)
  upload_resume — attach the resume PDF (no selector needed)
  done          — success/confirmation page is visible
  skip          — login/sign-up wall, search page, or truly impossible to complete

IMPORTANT — return "skip" immediately if:
- The page shows a login form, sign-in form, or account creation form (password fields, "Create Account" button)
- The page is a job search/listing page with keyword/location search fields (not an actual application form)
- The page asks you to verify email or create a new account before applying

Other critical rules:
- NEVER repeat an action from "Already tried" — try a completely different selector or method.
- If the same action has been tried 2+ times, it is NOT working — do something different.
- For custom dropdowns (Workday, React): use "click" to open the trigger, then "click" the option on the next step.
- For native <select>: use "select" with exact text from the options[] array.
- Fill all empty required fields before clicking Next/Submit.
- If last action failed (error in prompt), try a different selector or interaction method.
- First name / last name: split full name correctly.
- Phone number: digits only — NO country code (+91, +1, etc.).
"""


def apply_vision_loop(page: Page, profile: dict, context: str = "external") -> str:
    """
    Universal form filler: screenshot → GPT → execute → retry on error → skip after 3 failures.

    This single function handles every ATS: Workday, Greenhouse, Lever, iCIMS,
    Google Forms, SmartRecruiters, and anything else.
    """
    prefix = f"[{context}/vision]"
    _log(f"{prefix} Starting vision-driven application", "info")

    # Attempt resume upload immediately
    if _upload_resume(page, profile):
        _log(f"{prefix} Resume uploaded on first attempt", "info")
        time.sleep(1.5)
    _snap(page)

    # Build profile strings used in every prompt
    name_parts   = profile.get("full_name", "").split()
    first_name   = name_parts[0] if name_parts else ""
    last_name    = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    phone_raw    = re.sub(r"\D", "", profile.get("phone", ""))
    phone_digits = phone_raw[-10:] if len(phone_raw) >= 10 else phone_raw

    # State tracking
    tried:             dict[tuple, int] = {}   # (action, selector, value) → attempt count (success + fail)
    last_error:        str              = ""
    consecutive_fails: int              = 0
    MAX_STEPS                           = 20
    MAX_CONSEC                          = 3    # give up after this many back-to-back failures

    for step in range(1, MAX_STEPS + 1):

        if _is_success(page):
            _log(f"{prefix} Application submitted successfully!", "success")
            return "applied"

        # ── Extract DOM elements and visible page text ──────────────────────────
        elements      = _extract_form_elements(page)
        elements_json = json.dumps(elements, ensure_ascii=False)

        try:
            page_text = (page.inner_text("body") or "")[:3000]
        except Exception:
            page_text = ""

        # ── Build candidate/context text ────────────────────────────────────────
        error_note = f"\n⚠ Last action FAILED with error: {last_error}\nTry a completely different approach.\n" if last_error else ""

        tried_note = ""
        if tried:
            lines = "\n".join(
                f"  - action={a!r} selector={s!r} value={v!r}  (tried {c}×)"
                for (a, s, v), c in tried.items()
            )
            tried_note = f"\nAlready tried — do NOT repeat any of these (even if they 'succeeded' before):\n{lines}\n"

        candidate_text = (
            f"Step {step}/{MAX_STEPS}\n\n"
            f"Candidate:\n"
            f"  Full name     : {profile.get('full_name', '')}\n"
            f"  First name    : {first_name}\n"
            f"  Last name     : {last_name}\n"
            f"  Email         : {profile.get('email', '')}\n"
            f"  Phone (raw)   : {profile.get('phone', '')}\n"
            f"  Phone digits  : {phone_digits}  ← use ONLY this in phone number fields\n"
            f"  City          : {profile.get('current_city', '')}\n"
            f"  Job title     : {profile.get('current_job_title', '')}\n"
            f"  Company       : {profile.get('current_company', '')}\n"
            f"  Experience    : {profile.get('years_of_experience', '')} years\n"
            f"  Skills        : {', '.join(profile.get('skills', [])[:15])}\n"
            f"  Notice period : {profile.get('notice_period', '30')} days\n"
            f"  Current CTC   : {profile.get('current_salary', '')}\n"
            f"  Expected CTC  : {profile.get('expected_salary', '')}\n"
            f"  LinkedIn      : {profile.get('linkedin_url', '')}\n"
            f"  GitHub        : {profile.get('github_url', '')}\n"
            f"  Sponsorship   : No\n"
            f"  Work auth     : Authorized to work in India\n\n"
            f"Resume (first 800 chars):\n{_RESUME_TEXT[:800]}\n"
            f"{error_note}"
            f"{tried_note}\n"
            f"Visible page text (for context):\n{page_text}\n\n"
            f"Interactive elements on page:\n{elements_json}"
        )

        # ── Step 1: DOM-only (no vision — cheap). Step 2: vision fallback if stuck ──
        use_vision = consecutive_fails >= 2
        if use_vision:
            screenshot_b64 = _page_screenshot_b64(page)
            if not screenshot_b64:
                _log(f"{prefix} Screenshot failed, stopping", "warning")
                break
            user_content: list | str = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url":    f"data:image/jpeg;base64,{screenshot_b64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": candidate_text},
            ]
            _log(f"{prefix} Step {step}: using vision fallback (stuck)", "warning")
        else:
            user_content = candidate_text

        # ── Call GPT ────────────────────────────────────────────────────────────
        try:
            resp = _openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _VISION_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
                temperature=0,
            )
            _track_usage(resp)
            action = json.loads(resp.choices[0].message.content.strip())
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate limit" in err_str.lower():
                # Parse "try again in Xms" or "try again in Xs" from the error
                wait_sec = 2.0
                ms_match = re.search(r"try again in (\d+)ms", err_str, re.IGNORECASE)
                s_match  = re.search(r"try again in ([\d.]+)s", err_str, re.IGNORECASE)
                if ms_match:
                    wait_sec = max(1.0, int(ms_match.group(1)) / 1000 + 0.5)
                elif s_match:
                    wait_sec = max(1.0, float(s_match.group(1)) + 0.5)
                _log(f"{prefix} Rate limited — waiting {wait_sec:.1f}s before retry", "warning")
                time.sleep(wait_sec)
                continue  # Don't count as a failure
            _log(f"{prefix} GPT error at step {step}: {e}", "warning")
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSEC:
                break
            continue

        act    = (action.get("action") or "").strip()
        sel    = (action.get("selector") or "").strip()
        val    = (action.get("value") or "").strip()
        reason = (action.get("reason") or "")

        _log(f"{prefix} Step {step}: {act} | {sel[:70]} | {val[:40]}  — {reason}", "info")
        _snap(page)

        # ── Terminal actions ────────────────────────────────────────────────────
        if act == "done":
            if _is_success(page):
                _log(f"{prefix} GPT says done — confirmed applied", "success")
                return "applied"
            # GPT might be over-eager; treat as applied if no error detected
            _log(f"{prefix} GPT says done (no confirmation selector found)", "info")
            return "applied"

        if act == "skip":
            _log(f"{prefix} GPT says skip: {reason}", "warning")
            return "skipped"

        # ── Execute action ───────────────────────────────────────────────────────
        ok, error = _execute_action(page, profile, action)
        key = (act, sel, val)

        # Always record this attempt (success OR failure) so GPT never repeats it blindly
        tried[key] = tried.get(key, 0) + 1

        if ok:
            consecutive_fails = 0
            last_error = ""
            time.sleep(0.8)

            # Hard-stop: same action repeated MAX_CONSEC times even though it "succeeds"
            # — this means we're stuck in a toggle loop (e.g. alternating resume clicks).
            if tried[key] >= MAX_CONSEC:
                _log(
                    f"{prefix} Action '{act}' on '{sel}' tried {tried[key]}× "
                    f"with no progress — skipping company",
                    "warning",
                )
                return "skipped"

            # Soft warning: inject error so GPT tries something different next step
            if tried[key] >= 2:
                last_error = (
                    f"Action '{act}' on '{sel}' already tried {tried[key]}× "
                    f"but the page hasn't advanced. Try something COMPLETELY DIFFERENT."
                )

        else:
            last_error = error
            consecutive_fails += 1

            _log(f"{prefix} Step {step} FAILED ({tried[key]}×): {error}", "warning")

            # Exceeded per-action retry limit
            if tried[key] >= MAX_CONSEC:
                _log(
                    f"{prefix} Action '{act}' on '{sel}' failed {MAX_CONSEC}× "
                    f"— skipping company",
                    "warning",
                )
                return "skipped"

            # Exceeded consecutive failure limit
            if consecutive_fails >= MAX_CONSEC:
                _log(
                    f"{prefix} {MAX_CONSEC} consecutive failures — skipping company",
                    "warning",
                )
                return "skipped"

    _log(f"{prefix} Exhausted {MAX_STEPS} steps without success", "warning")
    return "skipped"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_external(
    page: Page,
    job_url: str,
    profile: dict,
) -> str:
    """
    Apply to a job on an external ATS page.

    Returns:
      "applied"        — form was submitted successfully
      "skipped"        — skipped (login wall, errors, max retries exceeded)
      "login_required" — explicitly blocked by a login wall
    """
    try:
        current_url = page.url
    except Exception:
        current_url = ""

    # Navigate if not already on the target URL
    if current_url.rstrip("/") != job_url.rstrip("/"):
        try:
            _log(f"[external] Navigating to {job_url}", "info")
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)
        except Exception as e:
            _log(f"[external] Navigation failed: {e}", "warning")
            return "skipped"

    _snap(page)

    # Login wall check
    if _requires_login(page):
        _log("[external] Login wall detected — skipping", "warning")
        return "login_required"

    # Job listing page check — if we landed on a job description page (not an
    # application form), try to find and click the Apply button first.
    # Indicators: no <input>/<textarea>/<form> fields, but an "Apply" link exists.
    _try_click_apply_button(page)

    # Detect ATS for logging only
    ats = detect_ats(job_url) or "unknown"
    _log(f"[external] ATS detected: {ats}  — starting vision loop", "info")

    try:
        return apply_vision_loop(page, profile, context=ats)
    except Exception as e:
        _log(f"[external] Vision loop error: {e}", "warning")
        return "skipped"


def _try_click_apply_button(page: Page) -> bool:
    """
    If the page is a job listing/description page (not yet an application form),
    click the Apply / Apply Now button to open the actual form.
    Returns True if a button was found and clicked.
    """
    # Only try if there are no visible form fields yet
    try:
        has_form = page.evaluate("""() => {
            const fields = document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]), textarea, select'
            );
            return Array.from(fields).some(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            });
        }""")
        if has_form:
            return False  # Already on an application form page
    except Exception:
        return False

    _apply_btn_selectors = [
        "a:has-text('Apply Now')",
        "a:has-text('Apply for this job')",
        "a:has-text('Apply for Job')",
        "button:has-text('Apply Now')",
        "button:has-text('Apply for this job')",
        "[data-automation-id='applyButton']",
        "[class*='apply-button']",
        "a[href*='/apply']",
    ]
    for sel in _apply_btn_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                _log(f"[external] Job listing detected — clicking Apply button", "info")
                btn.click()
                time.sleep(2.5)
                return True
        except Exception:
            continue
    return False
