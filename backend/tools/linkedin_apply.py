# """
# linkedin_apply.py
# -----------------
# Automatically applies to LinkedIn Easy Apply jobs using your profile.json.

# Flow:
#   Login → Search jobs (Easy Apply filter) → For each job:
#     → Click Easy Apply → Fill contact info → Upload resume
#     → Answer screening questions → Submit
# """

# from playwright.sync_api import sync_playwright
# from dotenv import load_dotenv
# from openai import OpenAI
# import base64
# import datetime
# import time
# import json
# import os
# import re
# import random

# import external_apply as _ext

# load_dotenv()

# _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# _ai_cache: dict = {}      # per-field GPT cache (legacy per-step path)
# _answer_cache: dict = {}  # session-level screening answer cache (Tier 2)

# # Set by server.py before calling run_automation(); None when running standalone.
# _logger = None

# # ── Token / cost tracking ─────────────────────────────────────────────────────
# # gpt-4o-mini pricing (per 1M tokens, as of 2025)
# _GPT_PRICE_INPUT  = 0.150 / 1_000_000   # $0.150 per 1M input tokens
# _GPT_PRICE_OUTPUT = 0.600 / 1_000_000   # $0.600 per 1M output tokens

# _total_input_tokens  = 0
# _total_output_tokens = 0

# def _track_usage(response) -> None:
#     """Record token usage from any OpenAI API response."""
#     global _total_input_tokens, _total_output_tokens
#     if response.usage:
#         _total_input_tokens  += response.usage.prompt_tokens
#         _total_output_tokens += response.usage.completion_tokens

# def _reset_usage() -> None:
#     global _total_input_tokens, _total_output_tokens
#     _total_input_tokens  = 0
#     _total_output_tokens = 0

# def _cost_summary() -> dict:
#     """Return token counts and USD cost for this run."""
#     cost = (
#         _total_input_tokens  * _GPT_PRICE_INPUT +
#         _total_output_tokens * _GPT_PRICE_OUTPUT
#     )
#     return {
#         "input_tokens":  _total_input_tokens,
#         "output_tokens": _total_output_tokens,
#         "total_tokens":  _total_input_tokens + _total_output_tokens,
#         "cost_usd":      round(cost, 6),
#     }

# def _log(message: str, log_type: str = "info") -> None:
#     """Send a log line to the WebSocket session (if connected) and stdout."""
#     if _logger is not None:
#         getattr(_logger, log_type, _logger.info)(message)
#     print(message)


# def _human_delay(min_ms: int = 200, max_ms: int = 700) -> None:
#     """Random pause to mimic human timing — reduces automation fingerprint."""
#     time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


# def _screenshot(page) -> None:
#     """
#     Fallback: capture a single frame and stream it to the frontend.
#     Used when CDPScreencaster is unavailable or as a supplementary snapshot.
#     """
#     if _logger is None or not hasattr(_logger, "screenshot"):
#         return
#     try:
#         img_bytes = page.screenshot(type="jpeg", quality=55, full_page=False)
#         _logger.screenshot(base64.b64encode(img_bytes).decode())
#     except Exception:
#         pass


# class CDPScreencaster:
#     """
#     Streams live browser frames to the frontend via the Chrome DevTools Protocol.

#     Chrome's ``Page.startScreencast`` command causes the browser to push a
#     compressed JPEG after every composited frame.  Each frame must be
#     acknowledged with ``Page.screencastFrameAck``; failure to do so causes
#     Chrome to pause the stream.

#     Integration with Playwright's sync API
#     ──────────────────────────────────────
#     Playwright's sync API is built on top of an internal asyncio event loop.
#     Every blocking sync call (``page.goto``, ``page.click``, ``page.fill``,
#     ``page.wait_for_selector``, ``page.wait_for_timeout``, …) yields control
#     back to that loop, which is when CDP events are dispatched and
#     ``_on_frame`` is invoked.  Between blocking Playwright calls (pure Python
#     computation, ``time.sleep``, OpenAI API calls), no CDP events arrive.
#     This is acceptable because the browser is not visually changing during
#     those periods.

#     Lifecycle
#     ─────────
#     1. Construct with the active Playwright ``Page`` and a ``SessionLogger``.
#     2. Call ``start()`` once; it is idempotent.
#     3. Frames stream automatically during all subsequent blocking Playwright
#        operations.
#     4. Call ``stop()`` in a ``finally`` block to release CDP resources cleanly.

#     Thread safety
#     ─────────────
#     All ``_on_frame`` invocations originate from Playwright's internal event
#     loop thread.  ``start()`` and ``stop()`` are called from the same
#     worker thread that owns the Playwright context.  No locking is required
#     because there is no cross-thread access to ``_session`` or ``_active``.
#     """

#     _MAX_FPS:    int = 10    # maximum frames forwarded to the frontend per second
#     _QUALITY:    int = 60    # JPEG quality sent to Chrome (0–100)
#     _MAX_WIDTH:  int = 1280  # Chrome will downscale frames to this width
#     _MAX_HEIGHT: int = 800

#     def __init__(self, page, logger) -> None:
#         self._page    = page
#         self._logger  = logger
#         self._session = None          # playwright CDPSession handle
#         self._active  = False         # True only between start() and stop()
#         self._last_ts = 0.0           # monotonic timestamp of the last forwarded frame

#     # ── Public API ────────────────────────────────────────────────────────────

#     def start(self) -> None:
#         """
#         Attach a CDP session to the page and begin the screencast.
#         Safe to call multiple times; subsequent calls are no-ops.
#         """
#         if self._active:
#             return
#         try:
#             self._session = self._page.context.new_cdp_session(self._page)
#             self._session.on("Page.screencastFrame", self._on_frame)
#             self._session.send("Page.startScreencast", {
#                 "format":        "jpeg",
#                 "quality":       self._QUALITY,
#                 "maxWidth":      self._MAX_WIDTH,
#                 "maxHeight":     self._MAX_HEIGHT,
#                 # Ask Chrome to emit every composited frame; we throttle in
#                 # _on_frame rather than relying on Chrome's own frame-skip
#                 # parameter, which is not well-defined across versions.
#                 "everyNthFrame": 1,
#             })
#             self._active = True
#             print("[CDPScreencaster] Screencast started.")
#         except Exception as exc:
#             # CDP may be unavailable in certain Playwright/browser configurations.
#             # Degrade gracefully: manual _screenshot() calls remain functional.
#             print(f"[CDPScreencaster] start() failed ({exc!r}); "
#                   "falling back to manual screenshots.")

#     def stop(self) -> None:
#         """
#         Stop the screencast and detach the CDP session.
#         Safe to call when not active; idempotent.
#         """
#         if not self._active:
#             return
#         self._active = False

#         # Best-effort: ignore errors caused by the browser already being closed.
#         try:
#             if self._session:
#                 self._session.send("Page.stopScreencast", {})
#         except Exception:
#             pass
#         try:
#             if self._session:
#                 self._session.detach()
#         except Exception:
#             pass

#         self._session = None
#         print("[CDPScreencaster] Screencast stopped.")

#     # ── Private ───────────────────────────────────────────────────────────────

#     def _on_frame(self, params: dict) -> None:
#         """
#         Invoked by Playwright for each ``Page.screencastFrame`` CDP event.

#         Chrome DevTools Protocol frame payload:
#           data      – base64-encoded JPEG string (the actual pixel data)
#           metadata  – dict: timestamp, deviceWidth, deviceHeight, scrollOffsetX/Y, …
#           sessionId – integer token; *must* be echoed back via screencastFrameAck
#                       or Chrome will pause the stream indefinitely
#         """
#         session_id: int = params.get("sessionId", 0)

#         # Acknowledge immediately so Chrome never stalls waiting for our ack,
#         # regardless of whether we forward this particular frame.
#         self._ack(session_id)

#         if not self._active or self._logger is None:
#             return

#         # Throttle: silently drop frames that arrive faster than _MAX_FPS.
#         now = time.monotonic()
#         if now - self._last_ts < 1.0 / self._MAX_FPS:
#             return
#         self._last_ts = now

#         try:
#             self._logger.screenshot(params["data"])
#         except Exception:
#             # Never let a delivery failure propagate into the automation loop.
#             pass

#     def _ack(self, session_id: int) -> None:
#         """Acknowledge a screencast frame to keep Chrome's stream flowing."""
#         try:
#             if self._session:
#                 self._session.send("Page.screencastFrameAck", {"sessionId": session_id})
#         except Exception:
#             pass


# def _send_company(index: int, title: str, company: str, location: str,
#                   status: str, reason: str = "",
#                   description: str = "", url: str = "") -> None:
#     """Send structured company result to the frontend companies table."""
#     if _logger is not None and hasattr(_logger, "company"):
#         _logger.company({
#             "index":       index,
#             "title":       title,
#             "company":     company,
#             "location":    location,
#             "status":      status,
#             "reason":      reason,
#             "description": description,
#             "url":         url,
#         })


# def load_resume_text() -> str:
#     path = os.path.join(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "resume_text.txt")
#     if os.path.exists(path):
#         with open(path, encoding="utf-8") as f:
#             return f.read()
#     return ""


# RESUME_TEXT = load_resume_text()


# def ask_user_fallback(question: str, options: list = None) -> str:
#     """
#     Ask the user directly in the terminal when AI cannot determine the answer.
#     Called in real-time while the browser is open.
#     """
#     print(f"\n  {'='*55}")
#     print(f"  [USER INPUT NEEDED — browser is paused]")
#     print(f"  Question: {question}")
#     if options:
#         print(f"  Available options:")
#         for i, opt in enumerate(options, 1):
#             print(f"    {i}. {opt}")
#         while True:
#             try:
#                 raw = input(f"  Enter number (1-{len(options)}) or type the exact answer: ").strip()
#                 if raw.isdigit() and 1 <= int(raw) <= len(options):
#                     chosen = options[int(raw) - 1]
#                     print(f"  You chose: {chosen}")
#                     print(f"  {'='*55}\n")
#                     return chosen
#                 elif raw:
#                     print(f"  You typed: {raw}")
#                     print(f"  {'='*55}\n")
#                     return raw
#             except (EOFError, KeyboardInterrupt):
#                 return options[0] if options else ""
#     else:
#         try:
#             ans = input(f"  Type your answer: ").strip()
#             print(f"  {'='*55}\n")
#             return ans
#         except (EOFError, KeyboardInterrupt):
#             return ""


# def get_ai_answer(question: str, field_type: str, profile: dict,
#                   options: list = None, ask_user_if_unsure: bool = True) -> str:
#     """
#     Ask GPT-4o-mini to answer a screening question using resume + profile context.
#     field_type: 'text', 'number', 'yes_no', 'dropdown'
#     options:    for dropdowns, the list of exact option strings to choose from
#     ask_user_if_unsure: if True and AI answer doesn't match any option, ask user via terminal
#     """
#     cache_key = f"{question}|{field_type}|{','.join(options or [])}"
#     if cache_key in _ai_cache:
#         return _ai_cache[cache_key]

#     options_block = ""
#     if options:
#         options_block = (
#             "\nAvailable options — you MUST return EXACTLY one of these strings, copied verbatim:\n"
#             + "\n".join(f"  - {o}" for o in options)
#         )

#     prompt = f"""You are filling a LinkedIn Easy Apply screening form on behalf of this candidate.
# Your goal: pick the answer that makes the candidate appear most qualified while staying truthful to their resume.

# --- CANDIDATE PROFILE ---
# Name: {profile['full_name']}
# Total experience: {profile.get('years_of_experience', '1')} years
# Current role: {profile['current_job_title']} at {profile['current_company']}
# City: {profile['current_city']}
# Notice period: {profile.get('notice_period', '30')} days
# Current salary (INR/year): {profile.get('current_salary', '')}
# Expected salary (INR/year): {profile.get('expected_salary', 700000)}
# LinkedIn: {profile.get('linkedin_url', '')}
# GitHub: {profile.get('github_url', '')}
# Phone: {profile['phone']}

# --- FULL RESUME ---
# {RESUME_TEXT}

# --- QUESTION ---
# {question}
# Field type: {field_type}
# {options_block}

# --- RULES ---
# - yes_no        → return exactly "Yes" or "No"
# - number        → return only a digit. NEVER return 0 for experience; minimum is 1.
#                   Check resume for the actual experience with the specific skill/tech mentioned.
# - text          → if options are given, short phrase; if no options (textarea / cover letter),
#                   write 2–4 professional sentences using the resume and profile above.
#                   Be specific, confident, and concise. Do NOT add a salutation or closing.
# - dropdown      → return EXACTLY one of the provided option strings, copied verbatim (case-sensitive).
#                   If experience options are present (e.g. "0-1 years", "1-2 years", "2+ years"),
#                   infer from resume internships; default to the lowest positive range (e.g. "0-1 years"
#                   or "1-2 years") for any tech found in resume.
# - Work authorization / eligibility in India → "Yes"
# - Notice period  → "30"
# - Salary         → "700000"
# - Current city   → "Delhi"
# - If a technology is NOT in the resume, pick the smallest/least-experience option available.
# - Return ONLY the answer — no explanation, no surrounding quotes or punctuation.
# """

#     # Textarea / cover-letter fields need room for a paragraph;
#     # all other field types fit comfortably in 60 tokens.
#     max_tok = 300 if field_type == "text" and not options else 60

#     try:
#         response = _openai_client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0,
#             max_tokens=max_tok,
#         )
#         _track_usage(response)
#         answer = response.choices[0].message.content.strip().strip('"').strip("'")
#         print(f"     AI answered '{question[:60]}' → '{answer}'")

#         # For dropdowns: validate AI returned a real option
#         if options and field_type == "dropdown":
#             # Exact match
#             if answer in options:
#                 _ai_cache[cache_key] = answer
#                 return answer
#             # Case-insensitive match
#             lower_map = {o.lower(): o for o in options}
#             if answer.lower() in lower_map:
#                 matched = lower_map[answer.lower()]
#                 _ai_cache[cache_key] = matched
#                 return matched
#             # Partial match (AI answer substring of option or vice-versa)
#             for opt in options:
#                 if answer.lower() in opt.lower() or opt.lower() in answer.lower():
#                     _ai_cache[cache_key] = opt
#                     print(f"     Partial match → '{opt}'")
#                     return opt
#             # Fuzzy word-overlap: score each option by how many words from
#             # the AI answer appear in the option text — pick highest scorer.
#             answer_words = set(re.split(r'\W+', answer.lower())) - {"", "the", "a", "an", "of", "with", "and", "or"}
#             best_opt, best_score = None, -1
#             for opt in options:
#                 opt_words = set(re.split(r'\W+', opt.lower()))
#                 score = len(answer_words & opt_words)
#                 if score > best_score:
#                     best_opt, best_score = opt, score
#             if best_opt and best_score > 0:
#                 _ai_cache[cache_key] = best_opt
#                 print(f"     Fuzzy match → '{best_opt}' (score {best_score})")
#                 return best_opt
#             # Change C: in server/headless mode skip ask_user_fallback;
#             # auto-pick the safest option without blocking stdin.
#             if ask_user_if_unsure:
#                 if _logger is not None:
#                     # Server mode: auto-pick affirmative option, or first option
#                     _YES_WORDS = {"yes", "y", "true", "1", "agree", "accept"}
#                     affirmative = next(
#                         (o for o in options if o.strip().lower() in _YES_WORDS), None
#                     )
#                     chosen = affirmative or options[0]
#                     print(f"     Server-mode auto-pick → '{chosen}' (AI returned '{answer}')")
#                     _ai_cache[cache_key] = chosen
#                     return chosen
#                 else:
#                     # Standalone terminal mode: ask user
#                     print(f"     AI answer '{answer}' didn't match any option — asking user.")
#                     user_ans = ask_user_fallback(question, options)
#                     _ai_cache[cache_key] = user_ans
#                     return user_ans
#             # Last resort: first option (placeholders already stripped by caller)
#             return options[0] if options else answer

#         _ai_cache[cache_key] = answer
#         return answer

#     except Exception as e:
#         print(f"     AI answer error: {e}")
#         if options and ask_user_if_unsure:
#             if _logger is not None:
#                 # Server mode: never block — pick first available real option
#                 return options[0] if options else ""
#             return ask_user_fallback(question, options)
#         return ""

# SCRIPT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# # Persistent browser profile — saves cookies/session so LinkedIn doesn't
# # trigger a security check on every run.
# BROWSER_PROFILE_DIR = os.path.join(SCRIPT_DIR, "linkedin_browser_profile")

# # =============================================
# # CONFIG
# # =============================================
# LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL")
# LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
# JOB_SEARCH_QUERY  = "Data Scientist"
# JOB_LOCATION      = "India"
# MAX_APPLICATIONS  = 20
# EASY_APPLY_ONLY   = True   # True = LinkedIn Easy Apply filter; False = all jobs (external apply)
# # =============================================


# def load_profile() -> dict:
#     path = os.path.join(SCRIPT_DIR, "profile.json")
#     if not os.path.exists(path):
#         raise FileNotFoundError("profile.json not found. Run parse_resume.py first.")
#     with open(path) as f:
#         return json.load(f)


# # ---------------------------------------------------------------------------
# # Login
# # ---------------------------------------------------------------------------

# def _js_fill_login(page) -> bool:
#     """Fill login form via JavaScript — bypasses Playwright visibility checks."""
#     return page.evaluate(f"""
#         (() => {{
#             const emailInput = (
#                 document.querySelector('input#session_key') ||
#                 document.querySelector('input#username') ||
#                 document.querySelector('input[name="session_key"]') ||
#                 document.querySelector('input[type="email"]') ||
#                 Array.from(document.querySelectorAll('input')).find(
#                     i => i.type === 'text' || i.type === 'email'
#                 )
#             );
#             const passInput = (
#                 document.querySelector('input#session_password') ||
#                 document.querySelector('input#password') ||
#                 document.querySelector('input[type="password"]')
#             );
#             if (!emailInput || !passInput) return false;

#             const nativeSetter = Object.getOwnPropertyDescriptor(
#                 window.HTMLInputElement.prototype, 'value'
#             ).set;

#             emailInput.focus();
#             nativeSetter.call(emailInput, {repr(LINKEDIN_EMAIL)});
#             emailInput.dispatchEvent(new Event('input',  {{ bubbles: true }}));
#             emailInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
#             emailInput.dispatchEvent(new Event('blur',   {{ bubbles: true }}));

#             passInput.focus();
#             nativeSetter.call(passInput, {repr(LINKEDIN_PASSWORD)});
#             passInput.dispatchEvent(new Event('input',  {{ bubbles: true }}));
#             passInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
#             passInput.dispatchEvent(new Event('blur',   {{ bubbles: true }}));
#             return true;
#         }})()
#     """)


# def login_linkedin(page) -> str:
#     """
#     Log in to LinkedIn with the credentials from environment variables.

#     Returns one of:
#       "success"            — logged in successfully
#       "wrong_credentials"  — LinkedIn rejected email/password
#       "checkpoint"         — security check / CAPTCHA required
#       "failed"             — login form not found or unknown error
#     """
#     print("Opening LinkedIn...")

#     # 'load' fires once HTML + resources are done — LinkedIn never reaches
#     # 'networkidle' because it streams background requests indefinitely.
#     try:
#         page.goto("https://www.linkedin.com/login",
#                   wait_until="load", timeout=30000)
#     except Exception:
#         pass  # page may still be usable after a timeout

#     # ── Already logged in? (persistent browser context keeps cookies) ─────────
#     # When the session cookie is still valid, LinkedIn redirects /login straight
#     # to the feed.  Detect that before waiting for a form that will never appear.
#     url_after_goto = page.url
#     if any(x in url_after_goto for x in ("feed", "/in/", "mynetwork", "jobs", "home")):
#         print("Already logged in (session cookie valid).")
#         _log("LinkedIn session restored from saved profile — skipping login.", "info")
#         return "success"

#     # Also check for checkpoint immediately after goto
#     if any(x in url_after_goto for x in ("checkpoint", "challenge", "captcha", "two-step", "pin")):
#         _log("LinkedIn security check detected on session restore.", "warning")
#         return "checkpoint"

#     # Wait until the REAL LinkedIn login form appears (email + password fields).
#     # We deliberately exclude generic input[type="text"] to avoid matching
#     # cookie-consent overlays or other React components that render first.
#     print("Waiting for login form...")
#     _LOGIN_FORM_JS = """() => !!(
#         document.querySelector('input#username') ||
#         document.querySelector('input#session_key') ||
#         document.querySelector('input[name="session_key"]') ||
#         document.querySelector('input[autocomplete="username"]') ||
#         document.querySelector('input[autocomplete="email"]')
#     )"""
#     try:
#         page.wait_for_function(_LOGIN_FORM_JS, timeout=25000)
#     except Exception:
#         url_now = page.url
#         if any(x in url_now for x in ("feed", "/in/", "mynetwork", "jobs", "home")):
#             print("Already logged in (redirected during wait).")
#             _log("LinkedIn session active — skipping login.", "info")
#             return "success"
#         # If the strict selectors timed out, fall back to any visible email-like input
#         # that has a name/id (not a nameless React overlay input)
#         _fallback_js = """() => {
#             const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="email"]'));
#             return inputs.some(i => i.name || i.id);
#         }"""
#         try:
#             page.wait_for_function(_fallback_js, timeout=5000)
#         except Exception:
#             print("Login form not detected.")
#             page.screenshot(path=os.path.join(SCRIPT_DIR, "linkedin_login_debug.png"))
#             if _logger is None:
#                 input("Please log in manually in the browser window, then press Enter here...")
#             return "failed"

#     time.sleep(1)

#     print("Entering credentials...")

#     # ── Helpers ───────────────────────────────────────────────────────────────

#     def _el_fill(selectors: list, value: str, label: str) -> bool:
#         """
#         Fill via ElementHandle.fill() — CDP-level, no visibility check,
#         properly updates React controlled component state.
#         Skips nameless/id-less inputs (React auto-IDs like :r0:) to avoid
#         filling overlay/cookie-banner inputs instead of the real login form.
#         """
#         for sel in selectors:
#             try:
#                 el = page.query_selector(sel)
#                 if el is None:
#                     continue
#                 attrs = el.evaluate(
#                     "e => ({id: e.id, name: e.name, placeholder: e.placeholder,"
#                     " autocomplete: e.autocomplete, type: e.type})"
#                 )
#                 # Skip nameless React overlay inputs (id like ':r0:' has no real name)
#                 el_id   = attrs.get("id", "")
#                 el_name = attrs.get("name", "")
#                 if not el_name and (not el_id or el_id.startswith(":")):
#                     print(f"  [{label}] skipping overlay input sel={sel} id={el_id!r}")
#                     continue
#                 print(f"  [{label}] sel={sel} → {attrs}")
#                 el.fill(value)
#                 time.sleep(0.25)
#                 return True
#             except Exception as _ex:
#                 print(f"  [{label}] sel={sel} error: {_ex}")
#                 continue
#         return False

#     # Real LinkedIn login selectors — ordered most-specific first
#     _email_sels = [
#         "input#username",
#         "input#session_key",
#         "input[name='session_key']",
#         "input[autocomplete='username']",
#         "input[autocomplete='email']",
#         "input[type='email']",
#         "input[type='text']",   # last resort — filtered by _el_fill overlay check
#     ]
#     _pass_sels = [
#         "input#session_password",
#         "input#password",
#         "input[name='session_password']",
#         "input[autocomplete='current-password']",
#         "input[type='password']",
#     ]

#     # ── Step 1: Fill email ────────────────────────────────────────────────────
#     _email_ok = _el_fill(_email_sels, LINKEDIN_EMAIL or "", "email")
#     print(f"Email fill: {'ok' if _email_ok else 'FAILED'}")

#     # ── Step 2: Check if password field exists (classic vs staged layout) ─────
#     _pass_exists = any(page.query_selector(s) is not None for s in _pass_sels)

#     # ── Step 3: Staged layout — click Continue to reveal password field ───────
#     if not _pass_exists:
#         print("Password field not in DOM — clicking Continue (staged layout)...")
#         _cont_sels = [
#             "button#login-submit",
#             "button[data-litms-control-urn*='login']",
#             "button.sign-in-form__submit-button",
#             "button:has-text('Continue')",
#             "button:has-text('Next')",
#             "button[type='submit']",
#         ]
#         for _csel in _cont_sels:
#             try:
#                 _cb = page.locator(_csel).first
#                 if _cb.is_visible():
#                     _cb.click()
#                     time.sleep(1.8)
#                     break
#             except Exception:
#                 continue

#     # ── Step 4: Fill password ─────────────────────────────────────────────────
#     _pass_ok = _el_fill(_pass_sels, LINKEDIN_PASSWORD or "", "password")
#     if not _pass_ok:
#         time.sleep(2)
#         _pass_ok = _el_fill(_pass_sels, LINKEDIN_PASSWORD or "", "password-retry")
#     print(f"Password fill: {'ok' if _pass_ok else 'FAILED'}")

#     if not _email_ok or not _pass_ok:
#         print(f"Credential fill incomplete (email={_email_ok}, password={_pass_ok}).")
#         page.screenshot(path=os.path.join(SCRIPT_DIR, "linkedin_login_debug.png"))
#         if _logger is None:
#             input("Log in manually then press Enter here...")
#         return "failed"

#     time.sleep(0.5)

#     # Submit the form
#     submitted = False
#     for sel in [
#         "button[type='submit']",
#         "button[data-litms-control-urn*='login']",
#         "button.sign-in-form__submit-button",
#         "button:has-text('Sign in')",
#     ]:
#         try:
#             btn = page.query_selector(sel)
#             if btn:
#                 btn.click()
#                 submitted = True
#                 break
#         except Exception:
#             continue

#     if not submitted:
#         try:
#             page.keyboard.press("Enter")
#         except Exception:
#             pass

#     # Wait for LinkedIn to respond — either redirect to feed or show an error
#     time.sleep(4)

#     url = page.url
#     print(f"Post-submit URL: {url}")

#     # ── Success: redirected to the main feed or profile ──────────────────────
#     if any(x in url for x in ("feed", "/in/", "mynetwork", "jobs")):
#         print("Login successful!")
#         _log("LinkedIn login successful.", "info")
#         return "success"

#     # ── Security checkpoint (CAPTCHA / unusual activity / 2FA) ───────────────
#     if any(x in url for x in ("checkpoint", "challenge", "captcha", "two-step", "pin")):
#         print("Security check required.")
#         _log("LinkedIn security check detected — please complete it in the browser.", "warning")
#         if _logger is None:
#             input("Complete the security check then press Enter...")
#         return "checkpoint"

#     # Also check body text for CAPTCHA / verification prompts
#     try:
#         _body = (page.inner_text("body") or "").lower()
#         _CHECKPOINT_PHRASES = [
#             "verify", "verification", "captcha", "security check",
#             "unusual activity", "confirm it's you", "let's do a quick",
#             "we need to verify", "complete this challenge", "prove you're not",
#         ]
#         if any(p in _body for p in _CHECKPOINT_PHRASES):
#             page.screenshot(path=os.path.join(SCRIPT_DIR, "linkedin_login_debug.png"))
#             _log("LinkedIn security verification required — please complete it in the browser.", "warning")
#             return "checkpoint"
#     except Exception:
#         pass

#     # ── Wrong credentials: detect LinkedIn's inline error messages ───────────
#     #
#     # LinkedIn shows errors in two ways:
#     #   1. Inline error spans with IDs  #error-for-password  /  #error-for-username
#     #   2. A red alert banner with class .alert or role="alert"
#     #
#     _WRONG_CRED_SELECTORS = [
#         "#error-for-password",
#         "#error-for-username",
#         "span#error-for-password",
#         "span#error-for-username",
#         ".form__label--error",
#         "[data-test-id='error-for-password']",
#     ]
#     _WRONG_CRED_PHRASES = [
#         "that's not the right password",
#         "incorrect password",
#         "wrong password",
#         "email address isn't associated",
#         "couldn't find a linkedin account",
#         "hmm, that's not the right password",
#         "please enter a valid email",
#         "incorrect email or password",
#     ]

#     for err_sel in _WRONG_CRED_SELECTORS:
#         try:
#             el = page.query_selector(err_sel)
#             if el and el.is_visible():
#                 err_text = (el.inner_text() or "").strip()
#                 print(f"Wrong credentials detected: {err_text}")
#                 _log(
#                     f"❌ LinkedIn login failed — wrong email or password. "
#                     f"Please check your credentials and try again. ({err_text})",
#                     "error",
#                 )
#                 return "wrong_credentials"
#         except Exception:
#             pass

#     try:
#         body_text = (page.inner_text("body") or "").lower()
#         for phrase in _WRONG_CRED_PHRASES:
#             if phrase in body_text:
#                 print(f"Wrong credentials phrase found: '{phrase}'")
#                 _log(
#                     "❌ LinkedIn login failed — wrong email or password. "
#                     "Please check your credentials and try again.",
#                     "error",
#                 )
#                 return "wrong_credentials"
#     except Exception:
#         pass

#     # ── Fallback: still on login page = rejected, unknown reason ─────────────
#     if "login" in url or "authwall" in url or "uas/login" in url:
#         page.screenshot(path=os.path.join(SCRIPT_DIR, "linkedin_login_debug.png"))
#         print(f"Login fallback screenshot saved → linkedin_login_debug.png")
#         _log(
#             "❌ LinkedIn login failed — credentials were not accepted. "
#             "Please verify your email and password.",
#             "error",
#         )
#         return "wrong_credentials"

#     # ── Unknown state ─────────────────────────────────────────────────────────
#     print(f"Login state unclear (URL: {url})")
#     _log(f"LinkedIn login state unclear (URL: {url}) — proceeding anyway.", "warning")
#     if _logger is None:
#         input("Press Enter to continue...")
#     return "success"   # optimistic: assume logged in on unknown URLs


# # ---------------------------------------------------------------------------
# # Job search
# # ---------------------------------------------------------------------------

# _EXTRACT_CARDS_JS = """
# () => {
#     const seen = new Set();
#     const results = [];
#     const cards = document.querySelectorAll(
#         '.job-card-container, .jobs-search-results__list-item'
#     );
#     for (const card of cards) {
#         const anchor = card.querySelector('a[href*="/jobs/view/"]');
#         if (!anchor) continue;
#         const url = anchor.href.split('?')[0];
#         if (seen.has(url)) continue;
#         seen.add(url);
#         const titleEl   = card.querySelector(
#             '.job-card-list__title--link, .job-card-list__title, '
#             + '.job-card-container__link span[aria-hidden="true"]'
#         );
#         const companyEl = card.querySelector(
#             '.job-card-container__primary-description, '
#             + '.artdeco-entity-lockup__subtitle span, '
#             + '.job-card-container__company-name'
#         );
#         const locationEl = card.querySelector(
#             '.job-card-container__metadata-item, '
#             + '.artdeco-entity-lockup__caption li'
#         );
#         results.push({
#             url:      url,
#             title:    titleEl    ? titleEl.innerText.trim()    : anchor.innerText.trim(),
#             company:  companyEl  ? companyEl.innerText.trim()  : '',
#             location: locationEl ? locationEl.innerText.trim() : '',
#         });
#     }
#     return results;
# }
# """

# def get_easy_apply_jobs(page, needed: int = 10) -> list[dict]:
#     """
#     Collect Easy Apply job cards by paginating LinkedIn's search results via
#     the ``&start=N`` URL parameter.

#     Why scrolling never worked reliably
#     ─────────────────────────────────────
#     LinkedIn's job list uses virtual DOM rendering in headless Chrome: only
#     the cards visible inside the viewport are kept in the DOM.  Changing a
#     panel's ``scrollTop`` in JavaScript does NOT fire the IntersectionObserver
#     callbacks that LinkedIn attaches to lazy-load new cards — so the DOM card
#     count never grew past whatever was rendered on the initial page load (7 in
#     this case).

#     Why URL pagination is the correct fix
#     ──────────────────────────────────────
#     LinkedIn exposes stable server-side pagination via ``&start=N`` (0, 25,
#     50 …).  Each page is a fresh server request that returns the next batch of
#     25 results fully rendered.  No scrolling, no IntersectionObserver, no
#     selector guessing — just load the next URL and extract cards.
#     """
#     _log(f"Searching for '{JOB_SEARCH_QUERY}' jobs in {JOB_LOCATION}...", "info")

#     base_url = (
#         f"https://www.linkedin.com/jobs/search/"
#         f"?keywords={JOB_SEARCH_QUERY.replace(' ', '%20')}"
#         f"&location={JOB_LOCATION.replace(' ', '%20')}"
#         f"&sortBy=R"           # sort by relevance
#     )
#     if EASY_APPLY_ONLY:
#         base_url += "&f_AL=true"   # LinkedIn's Easy Apply filter

#     seen_urls: set[str] = set()
#     all_jobs:  list[dict] = []

#     # LinkedIn shows up to 25 jobs per page.  Load just enough pages to
#     # satisfy ``needed``, plus one extra page as a buffer for deduplication.
#     pages_required = (needed // 25) + 2

#     for page_idx in range(pages_required):
#         if len(all_jobs) >= needed:
#             break

#         start  = page_idx * 25
#         url    = f"{base_url}&start={start}"

#         try:
#             page.goto(url, wait_until="load", timeout=30000)
#         except Exception:
#             pass

#         # Wait for at least one card to appear; bail out if the page is empty
#         try:
#             page.wait_for_selector(
#                 ".job-card-container, .jobs-search-results__list-item",
#                 timeout=10000,
#             )
#         except Exception:
#             _log(f"No job cards found on page {page_idx + 1} — stopping.", "warning")
#             break

#         time.sleep(1.5)   # let deferred JS finish rendering

#         batch = page.evaluate(_EXTRACT_CARDS_JS)
#         new_on_page = 0
#         for job in batch:
#             if job["url"] not in seen_urls:
#                 seen_urls.add(job["url"])
#                 all_jobs.append(job)
#                 new_on_page += 1

#         _log(f"Page {page_idx + 1}: found {new_on_page} new jobs "
#              f"(total so far: {len(all_jobs)})", "info")

#         if new_on_page == 0:
#             # LinkedIn returned a page with no new cards — end of results
#             break

#     # Trim to exactly what the user requested
#     jobs = all_jobs[:needed]
#     _log(f"Collected {len(jobs)} Easy Apply jobs (requested {needed})", "found")
#     for j in jobs:
#         print(f"   • {j['title']} @ {j['company']}  [{j['location']}]")
#     return jobs


# # ---------------------------------------------------------------------------
# # Easy Apply modal — vision-driven handler
# # ---------------------------------------------------------------------------

# _MODAL_VISION_SYSTEM = """You are an AI agent filling a LinkedIn Easy Apply form on behalf of a job candidate.
# You receive a list of interactive elements extracted from the modal DOM and the candidate's profile.
# Return the SINGLE best next action as JSON (no markdown, no code block):

# {
#   "action": "fill" | "typeahead" | "click" | "select" | "upload_resume" | "next" | "done",
#   "selector": "CSS selector for target element (empty for upload_resume / next / done)",
#   "value": "text to type OR exact option text from options[] (empty for click / next / done)",
#   "reason": "one sentence"
# }

# ━━━ ACTION RULES ━━━
#   fill          — type into plain text / email / tel / number / textarea fields
#   typeahead     — type into autocomplete/combobox fields (isTypeahead=true) — value is what to search for
#                   The system will type the value and select the first matching suggestion automatically.
#   click         — radio button LABELS, checkboxes, custom dropdown triggers, toggle buttons
#   select        — NATIVE <select> elements — value MUST be the EXACT option text from options[]
#   upload_resume — attach resume PDF (no selector needed)
#   next          — every required field on this page is correctly filled → click Next/Review/Submit
#   done          — a success / "Application submitted" confirmation is visible

# ━━━ FIELD-BY-FIELD GUIDANCE ━━━

# Text / email / phone:
#   - First name / last name: split full_name at the first space.
#   - Phone: use phone_digits (digits only, NO country code like +91 or +1).
#   - City / location: check isTypeahead — if true, use "typeahead" action with current_city value.
#   - Email: use the email from the candidate profile.

# Numeric "years of experience" fields:
#   - ALWAYS return a WHOLE INTEGER (e.g. 1, 2, 3). NEVER use decimals like 1.5 or 0.5.
#   - If the label asks about a SPECIFIC skill (e.g. "years with Python"):
#       • Use floor(years_of_experience) if the skill is in the candidate's skills list.
#       • Use 1 if the candidate has the skill but total experience is < 1 year.
#       • Use 0 only if the candidate genuinely does not have the skill.
#   - If the label asks for TOTAL years of experience: use floor(years_of_experience).

# Typeahead / autocomplete fields (isTypeahead = true):
#   - Use "typeahead" action. The system will type and select the first suggestion.
#   - City/location fields: type the city name (e.g. "Delhi", "Bangalore").
#   - Country fields: type "India".
#   - Company fields: type the company name from the profile.
#   - Skills fields: type the most relevant skill.

# Radio buttons / Yes-No questions:
#   - Sponsorship required / visa sponsorship: click "No".
#   - Authorized to work / work eligibility: click "Yes".
#   - Currently employed / working: click "Yes".
#   - Willing to relocate: click "Yes".
#   - Comfortable commuting / willing to work on-site: click "Yes".
#   - Any other Yes/No: use the most positive/qualified answer for a strong candidate.
#   - ALWAYS use selector for input[type="radio"] — the code will automatically find
#     and click the correct LABEL. Do NOT try to target label elements directly.

# Native <select> dropdowns:
#   - Use "select" action. Value MUST exactly match one entry from the options[] list.
#   - For notice period: pick the option closest to notice_period days.
#   - For currency / country: pick "India" / "INR" where relevant.
#   - For education level: pick the highest degree the candidate holds.
#   - For gender / demographic fields (optional): pick "Prefer not to say" or "Decline to self-identify".

# Custom dropdowns (non-native, not typeahead):
#   - Use "click" to open the trigger, then on the NEXT step "click" the matching option.

# Checkboxes:
#   - Use "click" on the label or the checkbox element.
#   - "Follow company" checkbox: skip it (it is optional — do not click it).

# Cover letter / additional info text areas:
#   - Write 2–3 concise sentences tailored to the role using the candidate's title and skills.

# Salary / CTC fields:
#   - current_salary → current_ctc value from profile.
#   - expected_salary → expected_ctc value from profile.
#   - If only annual CTC is asked, use the value as-is (do not divide).

# LinkedIn URL / GitHub URL / Portfolio:
#   - Fill with the exact URL from the profile (linkedin_url, github_url, portfolio_url).
#   - If a field is optional and the profile value is empty, skip it.

# Date fields (month/year):
#   - For "Date" type inputs, use fill with format "MM/YYYY" or "YYYY-MM" as shown by placeholder.
#   - If it's a select for month: select the month name or number. For year: select the 4-digit year.

# ━━━ CRITICAL RULES ━━━
# 1. Check the "currentValue" field of each element — if it is already correctly filled, SKIP that element.
# 2. Fill EVERY visible empty required field on this page before returning "next".
# 3. NEVER repeat an action from "Already tried" — choose a different selector or method.
# 4. If the last action failed, try a completely different approach (different selector, different action type).
# 5. Return "next" ONLY when ALL required fields are filled.
# 6. Return "done" ONLY when a success/confirmation message is visible on screen.
# 7. Do NOT interact with "Follow company" checkboxes — skip them.
# 8. For demographic/optional fields (gender, race, disability): always pick "Prefer not to say".
# """

# _SUCCESS_TEXTS = [
#     "your application was sent",
#     "application submitted",
#     "applied successfully",
#     "successfully applied",
#     "you've applied",
# ]

# _NAV_SELECTORS = [
#     "button[aria-label='Submit application']",
#     "button:has-text('Submit application')",
#     "button[aria-label='Continue to next step']",
#     "button[aria-label='Review your application']",
#     "button:has-text('Review')",
#     "button:has-text('Next')",
#     "button:has-text('Continue')",
#     "button:has-text('Save')",
#     "button[aria-label='Save']",
# ]


# def _modal_is_success(page) -> bool:
#     """Return True if LinkedIn shows an application-submitted confirmation."""
#     try:
#         body = (page.inner_text("body") or "").lower()
#         return any(t in body for t in _SUCCESS_TEXTS)
#     except Exception:
#         return False


# def _handle_resume_selection(page, profile: dict) -> bool:
#     """
#     Detect the LinkedIn resume-selection step (2+ resume cards visible) and
#     deterministically pick the uploaded CV — no GPT needed for this step.

#     LinkedIn shows:
#       • One card per uploaded resume  (label contains the filename)
#       • One card for "LinkedIn Profile" (auto-generated)

#     Strategy:
#       1. Try to match the card whose label text contains our uploaded filename.
#       2. Fall back to the first card that is NOT "LinkedIn Profile".
#       3. Last resort: pick whatever the first card is.

#     Returns True if this was a resume-selection page (handled + Next clicked).
#     Returns False if there were fewer than 2 cards (not a selection page).
#     """
#     try:
#         cards = page.query_selector_all("input[id^='jobsDocumentCardToggle']")
#         if len(cards) < 2:
#             return False

#         resume_path = profile.get("resume_path", "")
#         resume_name = os.path.basename(resume_path).lower() if resume_path else ""

#         chosen_label = None

#         # Pass 1 — match by uploaded filename
#         if resume_name:
#             for card in cards:
#                 cid   = card.get_attribute("id") or ""
#                 lid   = cid.replace("Toggle", "ToggleLabel")
#                 label = page.query_selector(f"#{lid}") or page.query_selector(f"label[for='{cid}']")
#                 if label:
#                     txt = (label.inner_text() or "").lower()
#                     # Match on first ~12 chars of filename (avoids extension issues)
#                     if resume_name[:12] in txt:
#                         chosen_label = label
#                         break

#         # Pass 2 — any non-LinkedIn-profile card
#         if not chosen_label:
#             for card in cards:
#                 cid   = card.get_attribute("id") or ""
#                 lid   = cid.replace("Toggle", "ToggleLabel")
#                 label = page.query_selector(f"#{lid}") or page.query_selector(f"label[for='{cid}']")
#                 if label:
#                     txt = (label.inner_text() or "").lower()
#                     if "linkedin" not in txt and "profile" not in txt:
#                         chosen_label = label
#                         break

#         # Pass 3 — just take the first card
#         if not chosen_label and cards:
#             cid   = cards[0].get_attribute("id") or ""
#             lid   = cid.replace("Toggle", "ToggleLabel")
#             chosen_label = (
#                 page.query_selector(f"#{lid}") or
#                 page.query_selector(f"label[for='{cid}']")
#             )

#         if chosen_label:
#             try:
#                 chosen_label.scroll_into_view_if_needed()
#                 chosen_label.click()
#                 time.sleep(0.5)
#                 _log("     [modal] Resume card selected — clicking Next", "info")
#             except Exception:
#                 pass

#         # Click Next/Submit to advance past the resume selection page
#         _modal_click_next(page)
#         time.sleep(2)
#         return True

#     except Exception:
#         return False


# def _modal_screenshot_b64(page) -> str:
#     try:
#         raw = page.screenshot(type="jpeg", quality=65, full_page=False)
#         return base64.b64encode(raw).decode()
#     except Exception:
#         return ""


# def _modal_elements(page) -> list:
#     """Visible interactive elements inside the Easy Apply modal."""
#     try:
#         return page.evaluate("""() => {
#             const MAX = 60;
#             const modal = document.querySelector('.jobs-easy-apply-content')
#                        || document.querySelector('[role="dialog"]')
#                        || document;

#             // Returns the most descriptive label text for an element,
#             // walking up to 8 ancestors to find fieldset legend or label.
#             const getLabel = (el) => {
#                 if (el.id) {
#                     const lbl = document.querySelector(`label[for='${el.id}']`);
#                     if (lbl) return lbl.innerText.trim().slice(0, 120);
#                 }
#                 const lblId = el.getAttribute('aria-labelledby');
#                 if (lblId) {
#                     const parts = lblId.split(/\\s+/).map(id => {
#                         const n = document.getElementById(id);
#                         return n ? n.innerText.trim() : '';
#                     }).filter(Boolean);
#                     if (parts.length) return parts.join(' ').slice(0, 120);
#                 }
#                 // aria-label is authoritative when present
#                 const aria = el.getAttribute('aria-label');
#                 if (aria) return aria.slice(0, 120);
#                 let p = el.parentElement;
#                 for (let i = 0; i < 8 && p; i++, p = p.parentElement) {
#                     if (p.tagName === 'LABEL') return p.innerText.trim().slice(0, 120);
#                     if (p.tagName === 'FIELDSET') {
#                         const leg = p.querySelector('legend');
#                         if (leg) return leg.innerText.trim().slice(0, 120);
#                     }
#                     // LinkedIn wraps questions in <div class="fb-form-element">
#                     const heading = p.querySelector('label, legend, h3, h4, [class*="label"]');
#                     if (heading && heading !== el) return heading.innerText.trim().slice(0, 120);
#                 }
#                 return el.getAttribute('placeholder') || '';
#             };

#             const isVisible = (el) => {
#                 const r = el.getBoundingClientRect();
#                 return r.width > 0 && r.height > 0
#                     && getComputedStyle(el).display !== 'none'
#                     && getComputedStyle(el).visibility !== 'hidden';
#             };

#             // Detect LinkedIn typeahead / autocomplete inputs
#             // These need special handling: type → wait for dropdown → click option
#             const isTypeahead = (el) => {
#                 return (
#                     el.getAttribute('role') === 'combobox' ||
#                     el.getAttribute('aria-autocomplete') === 'list' ||
#                     el.getAttribute('aria-autocomplete') === 'both' ||
#                     el.getAttribute('autocomplete') === 'off' && el.getAttribute('aria-expanded') !== null ||
#                     el.classList.contains('basic-typeahead__raw-input') ||
#                     !!el.closest('[data-js-typeahead-input]') ||
#                     !!el.closest('.basic-typeahead')
#                 );
#             };

#             const results = [];
#             for (const el of modal.querySelectorAll('input, textarea, select, button, label')) {
#                 if (!isVisible(el)) continue;
#                 const tag  = el.tagName.toLowerCase();
#                 const type = (el.getAttribute('type') || tag).toLowerCase();
#                 if (type === 'hidden') continue;

#                 // Build the most stable selector:
#                 // Priority: aria-label > id > name > data-test-id > tag
#                 let sel = tag;
#                 const ariaLabelAttr = el.getAttribute('aria-label');
#                 if (el.id && !el.id.includes(':')) {
#                     // Only use #id when it has no CSS-special chars like ':'
#                     sel = `#${el.id}`;
#                 } else if (ariaLabelAttr) {
#                     // aria-label selectors are stable across LinkedIn A/B tests
#                     sel = `${tag}[aria-label='${ariaLabelAttr.replace(/'/g, "\\'")}']`;
#                 } else if (el.getAttribute('name')) {
#                     sel = `${tag}[name='${el.getAttribute('name')}']`;
#                 } else if (el.getAttribute('data-test-id')) {
#                     sel = `[data-test-id='${el.getAttribute('data-test-id')}']`;
#                 } else if (el.id) {
#                     // ID with special chars — use attribute selector
#                     sel = `[id='${el.id}']`;
#                 }

#                 let options = [];
#                 if (tag === 'select') {
#                     options = Array.from(el.options)
#                         .map(o => o.text.trim())
#                         .filter(t => t && !['select','select an option','please select','--','select one','choose'].includes(t.toLowerCase()));
#                 }

#                 // For radio/checkbox: whether it is currently checked
#                 const checked = (type === 'radio' || type === 'checkbox') ? el.checked : undefined;

#                 results.push({
#                     selector:    sel,
#                     tag,
#                     type,
#                     label:       getLabel(el),
#                     placeholder: el.getAttribute('placeholder') || '',
#                     ariaLabel:   ariaLabelAttr || '',
#                     // For <select>: show the visible display text, not the raw value attribute.
#                     // This lets the LLM correctly identify already-selected options
#                     // (e.g. "India (+91)") without needing to know internal option values.
#                     currentValue: tag === 'select'
#                         ? (el.selectedIndex >= 0 && el.options[el.selectedIndex]
#                             ? el.options[el.selectedIndex].text.trim()
#                             : '')
#                         : (el.value || el.innerText?.trim().slice(0, 80) || ''),
#                     checked,
#                     required:    el.required || el.getAttribute('aria-required') === 'true',
#                     hasError:    !!el.closest('.artdeco-inline-feedback--error, .fb-form-element--error'),
#                     isTypeahead: isTypeahead(el),
#                     options,
#                 });
#                 if (results.length >= MAX) break;
#             }
#             return results;
#         }""")
#     except Exception:
#         return []


# def _safe_locator(page, selector: str):
#     """
#     Return a Playwright locator that works even when the selector contains
#     characters that are special in CSS (e.g. LinkedIn's URN-based IDs which
#     contain ':', '(', ')').

#     Conversions applied:
#       • #id-with-specials  →  [id="id-with-specials"]
#       • label:contains('X') →  label:has-text("X")   (jQuery → Playwright)
#     """
#     # Fix jQuery :contains() → Playwright :has-text()
#     selector = re.sub(r":contains\(['\"]?(.*?)['\"]?\)", r':has-text("\1")', selector)

#     # If this looks like an ID selector with special CSS characters, use attribute selector
#     if selector.startswith("#") and any(c in selector for c in ":()[]|,+~>"):
#         raw_id = selector[1:]
#         return page.locator(f'[id="{raw_id}"]')

#     return page.locator(selector)


# def _modal_execute(page, profile: dict, action: dict) -> tuple[bool, str]:
#     """
#     Execute a GPT action inside the LinkedIn Easy Apply modal.
#     Returns (success, error_msg).
#     """
#     act      = (action.get("action") or "").strip()
#     selector = (action.get("selector") or "").strip()
#     value    = (action.get("value") or "").strip()

#     try:
#         if act == "upload_resume":
#             resume_path = profile.get("resume_path", "")
#             if not resume_path or not os.path.exists(resume_path):
#                 return (False, "resume_path missing or file not found")
#             try:
#                 fi = page.wait_for_selector("input[type='file']", timeout=3000, state="attached")
#                 if fi:
#                     fi.set_input_files(resume_path)
#                     time.sleep(0.8)
#                     return (True, "")
#                 return (False, "No file input found")
#             except Exception as e:
#                 return (False, str(e))

#         if not selector:
#             return (False, f"No selector for action '{act}'")

#         if act == "typeahead":
#             # Typeahead/autocomplete inputs: type slowly to trigger suggestions,
#             # then click the first matching option or press Enter/ArrowDown.
#             try:
#                 loc = _safe_locator(page, selector).first
#                 loc.wait_for(state="visible", timeout=4000)
#                 loc.scroll_into_view_if_needed()
#                 loc.click()
#                 page.wait_for_timeout(200)
#                 # Clear existing value first
#                 page.keyboard.press("Control+a")
#                 page.keyboard.press("Delete")
#                 page.wait_for_timeout(150)
#                 # Type the search value character by character with small delays
#                 page.keyboard.type(str(value), delay=60)
#                 page.wait_for_timeout(900)   # wait for dropdown to populate

#                 # Try to click the first matching option in the suggestion list
#                 val_lower = str(value).lower()
#                 found_option = False
#                 for opt_sel in [
#                     f'[role="option"]:has-text("{value}")',
#                     '[role="option"]',
#                     f'li[role="listitem"]:has-text("{value}")',
#                     '.basic-typeahead__selectable:has-text("{value}")',
#                     '.basic-typeahead__selectable',
#                 ]:
#                     try:
#                         opt = page.locator(opt_sel).first
#                         if opt.count() > 0 and opt.is_visible():
#                             opt.click(timeout=2000)
#                             page.wait_for_timeout(400)
#                             found_option = True
#                             break
#                     except Exception:
#                         continue

#                 if not found_option:
#                     # Press ArrowDown + Enter to select first suggestion
#                     page.keyboard.press("ArrowDown")
#                     page.wait_for_timeout(300)
#                     page.keyboard.press("Enter")
#                     page.wait_for_timeout(400)

#                 return (True, "")
#             except Exception as e:
#                 return (False, str(e))

#         if act == "fill":
#             try:
#                 loc = _safe_locator(page, selector).first
#                 loc.wait_for(state="visible", timeout=4000)
#                 loc.scroll_into_view_if_needed()

#                 # Special handling for date inputs
#                 input_type = ""
#                 try:
#                     input_type = (loc.get_attribute("type") or "").lower()
#                 except Exception:
#                     pass

#                 if input_type == "date":
#                     # HTML date inputs require YYYY-MM-DD format
#                     date_val = str(value)
#                     # If user gave MM/YYYY convert to YYYY-MM-01
#                     m = re.match(r"(\d{1,2})/(\d{4})", date_val)
#                     if m:
#                         date_val = f"{m.group(2)}-{m.group(1).zfill(2)}-01"
#                     try:
#                         loc.fill(date_val)
#                         page.wait_for_timeout(400)
#                         return (True, "")
#                     except Exception:
#                         pass

#                 # ── Approach 1: keyboard (React-aware) ───────────────────────────
#                 # click → select-all → type char-by-char → Tab
#                 # Tab fires onBlur which commits React state for ALL input types,
#                 # not just number/tel. Must always press Tab.
#                 loc.click()
#                 page.keyboard.press("Control+a")
#                 page.keyboard.type(str(value))
#                 page.keyboard.press("Tab")   # always — commits React state via onBlur
#                 page.wait_for_timeout(500)

#                 # ── Verify approach 1 worked ──────────────────────────────────────
#                 try:
#                     actual = loc.input_value()
#                 except Exception:
#                     actual = str(value)   # can't verify input_value — assume ok

#                 if actual.strip() != "" and actual.strip() == str(value).strip():
#                     return (True, "")   # keyboard approach succeeded

#                 # ── Approach 2: JS native-setter (React fiber) ───────────────────
#                 # Sets value via React's internal prototype setter, then fires the
#                 # full event chain React expects: input → change → blur.
#                 loc.evaluate("""(el, val) => {
#                     el.focus();
#                     const proto = el.tagName === 'TEXTAREA'
#                         ? HTMLTextAreaElement.prototype
#                         : HTMLInputElement.prototype;
#                     const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
#                     if (setter) setter.call(el, val);
#                     el.dispatchEvent(new InputEvent('input',  { bubbles: true, data: val }));
#                     el.dispatchEvent(new Event('change', { bubbles: true }));
#                     // React 16/17 fiber props
#                     const rk = Object.keys(el).find(
#                         k => k.startsWith('__reactProps') || k.startsWith('__reactFiber')
#                     );
#                     if (rk && el[rk] && el[rk].onChange) {
#                         el[rk].onChange({ target: el, currentTarget: el });
#                     }
#                     el.dispatchEvent(new Event('blur', { bubbles: true }));
#                 }""", str(value))
#                 page.wait_for_timeout(400)

#                 # ── Verify approach 2 worked ──────────────────────────────────────
#                 try:
#                     actual2 = loc.input_value()
#                 except Exception:
#                     actual2 = str(value)

#                 if actual2.strip() == "":
#                     return (False, f"Value '{value}' did not persist after keyboard+JS fill (React may have rejected it)")

#                 return (True, "")
#             except Exception as e:
#                 return (False, str(e))

#         elif act == "click":
#             try:
#                 loc = _safe_locator(page, selector).first
#                 # Use "attached" first so we can scroll before checking visibility.
#                 # An element can be in the DOM but off-screen; scrolling it into
#                 # view makes it visible for the subsequent click.
#                 loc.wait_for(state="attached", timeout=4000)
#                 try:
#                     loc.scroll_into_view_if_needed()
#                     page.wait_for_timeout(300)
#                 except Exception:
#                     pass
#                 if not loc.is_visible():
#                     raise Exception("element not visible after scroll — it may have been removed from DOM")
#                 _human_delay(80, 200)

#                 # ── Radio button special handling ─────────────────────────────
#                 # LinkedIn radio inputs must be activated via their LABEL —
#                 # clicking the <input type="radio"> directly does not fire
#                 # React's onChange and the selection never registers.
#                 # Strategy:
#                 #   1. If GPT gave a radio input selector → find the label by
#                 #      (a) label[for=id], (b) parent label, (c) sibling label
#                 #      that contains the wanted value text, then click THAT.
#                 #   2. Fall back to a JS-dispatch that fires both the native
#                 #      click and React's synthetic event on the input.
#                 el_type = ""
#                 try:
#                     el_type = (loc.get_attribute("type") or "").lower()
#                 except Exception:
#                     pass

#                 if el_type == "radio":
#                     clicked_radio = False

#                     # (a) Try to click a label that wraps or is associated with
#                     #     this radio and contains the target value text
#                     try:
#                         el_id = loc.get_attribute("id") or ""
#                         el_name = loc.get_attribute("name") or ""
#                         el_val  = loc.get_attribute("value") or value or ""

#                         # Look for sibling/parent labels containing the value text
#                         candidates = []
#                         if el_id:
#                             candidates.append(f"label[for='{el_id}']")
#                         if el_name and value:
#                             candidates.append(
#                                 f"label:has(input[name='{el_name}'][value='{el_val}'])"
#                             )
#                         if value:
#                             candidates.append(f"label:has-text('{value}')")

#                         for lbl_sel in candidates:
#                             try:
#                                 lbl = page.locator(lbl_sel).first
#                                 if lbl.count() > 0 and lbl.is_visible():
#                                     lbl.scroll_into_view_if_needed()
#                                     lbl.click(timeout=3000)
#                                     page.wait_for_timeout(400)
#                                     clicked_radio = True
#                                     break
#                             except Exception:
#                                 continue
#                     except Exception:
#                         pass

#                     # (b) JS fallback: fire click + React synthetic event on input
#                     if not clicked_radio:
#                         try:
#                             loc.evaluate("""(el) => {
#                                 el.checked = true;
#                                 el.dispatchEvent(new MouseEvent('click',  { bubbles: true }));
#                                 el.dispatchEvent(new Event('change', { bubbles: true }));
#                                 const rk = Object.keys(el).find(
#                                     k => k.startsWith('__reactProps') || k.startsWith('__reactFiber')
#                                 );
#                                 if (rk && el[rk] && el[rk].onChange) {
#                                     el[rk].onChange({ target: el, currentTarget: el });
#                                 }
#                             }""")
#                             page.wait_for_timeout(400)
#                             clicked_radio = True
#                         except Exception:
#                             pass

#                     if clicked_radio:
#                         return (True, "")
#                     # Fall through to normal click if radio-specific path failed

#                 # ── Normal click ──────────────────────────────────────────────
#                 try:
#                     loc.click(timeout=4000)
#                 except Exception:
#                     loc.dispatch_event("click")
#                 page.wait_for_timeout(400)
#                 return (True, "")
#             except Exception as e:
#                 # Fallback 1: try by visible text if selector looks like plain text
#                 if not any(c in selector for c in "#.[]:>~+=^$*()|,"):
#                     try:
#                         page.locator(f"text={selector}").first.click(timeout=2000)
#                         return (True, "")
#                     except Exception:
#                         pass
#                 # Fallback 2: JS click (bypasses pointer-events:none overlays)
#                 try:
#                     el = page.query_selector(selector)
#                     if el:
#                         page.evaluate("el => el.click()", el)
#                         page.wait_for_timeout(400)
#                         return (True, "")
#                 except Exception:
#                     pass
#                 return (False, str(e))

#         elif act == "select":
#             try:
#                 loc = _safe_locator(page, selector).first

#                 # For truncated IDs: try starts-with match as fallback
#                 try:
#                     loc.wait_for(state="visible", timeout=3000)
#                 except Exception:
#                     if selector.startswith("#") and len(selector) > 20:
#                         partial = selector[1:60]
#                         loc = page.locator(f'[id^="{partial}"]').first
#                         loc.wait_for(state="visible", timeout=3000)

#                 # Detect element type: native <select> vs LinkedIn custom dropdown
#                 tag_name = loc.evaluate("el => el.tagName.toLowerCase()")

#                 if tag_name == "select":
#                     # ── Read real options from DOM first ─────────────────────
#                     # GPT may return an option text that doesn't exactly match
#                     # (e.g. "Prefer not to say" vs "Decline to Self-Identify").
#                     # We resolve GPT's answer to the closest REAL option before
#                     # attempting any selection — never trust the raw GPT string.
#                     real_options: list[str] = loc.evaluate("""el =>
#                         Array.from(el.options)
#                             .map(o => o.text.trim())
#                             .filter(t => t && !['select','select an option',
#                                 'please select','--','select one','choose',
#                                 ''].includes(t.toLowerCase()))
#                     """)

#                     def _best_match(wanted: str, choices: list[str]) -> str | None:
#                         if not choices:
#                             return None
#                         w = wanted.strip().lower()
#                         # 1. Exact match
#                         for c in choices:
#                             if c.strip().lower() == w:
#                                 return c
#                         # 2. GPT answer is substring of option or vice-versa
#                         for c in choices:
#                             cl = c.strip().lower()
#                             if w in cl or cl in w:
#                                 return c
#                         # 3. Word-overlap score
#                         stop = {"", "the", "a", "an", "of", "to", "not", "or",
#                                 "and", "self", "say", "identify", "prefer",
#                                 "decline", "disclose", "would", "rather"}
#                         w_words = set(re.split(r'\W+', w)) - stop
#                         best, best_score = None, -1
#                         for c in choices:
#                             c_words = set(re.split(r'\W+', c.lower())) - stop
#                             score = len(w_words & c_words)
#                             if score > best_score:
#                                 best, best_score = c, score
#                         return best if best_score > 0 else choices[0]

#                     resolved = _best_match(value, real_options) or value
#                     if resolved != value:
#                         _log(
#                             f"     [modal] select resolved '{value}' → '{resolved}' "
#                             f"(from {len(real_options)} real options)",
#                             "info",
#                         )

#                     # ── Native <select>: React-aware setter ──────────────────
#                     ok = loc.evaluate("""(selectEl, label) => {
#                         const opts = Array.from(selectEl.options);
#                         const match = opts.find(o =>
#                             o.text.trim().toLowerCase() === label.toLowerCase() ||
#                             o.text.trim().toLowerCase().includes(label.toLowerCase()) ||
#                             label.toLowerCase().includes(o.text.trim().toLowerCase())
#                         );
#                         if (!match) return false;
#                         const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
#                         setter.call(selectEl, match.value);
#                         selectEl.dispatchEvent(new Event('input',  { bubbles: true }));
#                         selectEl.dispatchEvent(new Event('change', { bubbles: true }));
#                         const pk = Object.keys(selectEl).find(k => k.startsWith('__reactProps'));
#                         if (pk && selectEl[pk].onChange) {
#                             selectEl[pk].onChange({ target: selectEl, currentTarget: selectEl });
#                         }
#                         return true;
#                     }""", resolved)
#                     if ok:
#                         page.wait_for_timeout(400)
#                         return (True, "")
#                     # Standard fallback using the resolved option text
#                     try:
#                         loc.select_option(label=resolved, timeout=2000)
#                         page.wait_for_timeout(400)
#                         return (True, "")
#                     except Exception:
#                         try:
#                             loc.select_option(value=resolved, timeout=2000)
#                             page.wait_for_timeout(400)
#                             return (True, "")
#                         except Exception as e2:
#                             return (False, f"native select failed for '{resolved}': {e2}")

#                 else:
#                     # ── LinkedIn custom multipleChoice / Workday-style dropdown ──
#                     # Pattern: click to open → listbox appears → click matching option
#                     try:
#                         loc.scroll_into_view_if_needed()
#                         loc.click()
#                         page.wait_for_timeout(600)
#                     except Exception:
#                         loc.dispatch_event("click")
#                         page.wait_for_timeout(600)

#                     # Find matching option in the opened listbox
#                     val_lower = value.lower()
#                     for opt_sel in [
#                         f'[role="option"]:has-text("{value}")',
#                         f'li:has-text("{value}")',
#                         f'span:has-text("{value}")',
#                         f'button:has-text("{value}")',
#                     ]:
#                         try:
#                             opt = page.locator(opt_sel).first
#                             if opt.count() > 0:
#                                 opt.click(timeout=2000)
#                                 page.wait_for_timeout(400)
#                                 return (True, "")
#                         except Exception:
#                             continue

#                     # Fallback: find any visible option containing the value text
#                     try:
#                         opts = page.query_selector_all('[role="option"], li[class*="option"]')
#                         for opt in opts:
#                             if opt.is_visible() and val_lower in (opt.inner_text() or "").lower():
#                                 opt.click()
#                                 page.wait_for_timeout(400)
#                                 return (True, "")
#                     except Exception:
#                         pass

#                     # Close the dropdown and report failure
#                     try:
#                         page.keyboard.press("Escape")
#                     except Exception:
#                         pass
#                     return (False, f"Custom dropdown option '{value}' not found in opened listbox")

#             except Exception as e:
#                 return (False, str(e))

#         else:
#             return (False, f"Unknown action: {act}")

#     except Exception as e:
#         return (False, f"_modal_execute error: {e}")


# def _modal_click_next(page) -> bool:
#     """Click the Next / Review / Submit button. Returns True if found."""
#     for sel in _NAV_SELECTORS:
#         try:
#             btn = page.query_selector(sel)
#             if btn and btn.is_visible() and btn.is_enabled():
#                 try:
#                     btn.scroll_into_view_if_needed()
#                 except Exception:
#                     pass
#                 _human_delay(100, 300)
#                 btn.click()
#                 return True
#         except Exception:
#             pass
#     return False


# # ─────────────────────────────────────────────────────────────────────────────
# # Smart-fill helpers — Tier 1 (profile), Tier 2 (cache), Tier 3 (GPT screening)
# # ─────────────────────────────────────────────────────────────────────────────

# def _normalize_cache_key(text: str) -> str:
#     """Lowercase + strip punctuation + collapse spaces → stable cache key."""
#     text = (text or "").lower().strip()
#     text = re.sub(r"[^\w\s]", " ", text)
#     return re.sub(r"\s+", " ", text).strip()


# def _extract_phone_digits(profile: dict) -> str:
#     """Return last 10 digits of the candidate's phone number."""
#     raw = re.sub(r"\D", "", profile.get("phone", ""))
#     return raw[-10:] if len(raw) >= 10 else raw


# # ── Profile field patterns ────────────────────────────────────────────────────
# # Each tuple: (phrase_to_find_in_label, human_key_desc, value_extractor(profile) → str)
# # Ordered from most-specific to least-specific so longer phrases match first.
# _PROFILE_FIELD_PATTERNS: list[tuple] = [
#     ("first name",            "first_name",         lambda p: ((p.get("full_name") or "").split() or [""])[0]),
#     ("last name",             "last_name",           lambda p: " ".join((p.get("full_name") or "").split()[1:]) or ""),
#     ("family name",           "last_name",           lambda p: " ".join((p.get("full_name") or "").split()[1:]) or ""),
#     ("surname",               "last_name",           lambda p: " ".join((p.get("full_name") or "").split()[1:]) or ""),
#     ("full name",             "full_name",           lambda p: p.get("full_name") or ""),
#     ("notice period",         "notice_period",       lambda p: str(p.get("notice_period") or "30")),
#     ("current ctc",           "current_salary",      lambda p: str(p.get("current_salary") or "")),
#     ("current salary",        "current_salary",      lambda p: str(p.get("current_salary") or "")),
#     ("current compensation",  "current_salary",      lambda p: str(p.get("current_salary") or "")),
#     ("expected ctc",          "expected_salary",     lambda p: str(p.get("expected_salary") or "")),
#     ("expected salary",       "expected_salary",     lambda p: str(p.get("expected_salary") or "")),
#     ("desired salary",        "expected_salary",     lambda p: str(p.get("expected_salary") or "")),
#     # Only "total" / "overall" experience maps to profile — skill-specific questions go to GPT
#     ("total years",           "years_of_experience", lambda p: str(int(float(p.get("years_of_experience") or "1")))),
#     ("total experience",      "years_of_experience", lambda p: str(int(float(p.get("years_of_experience") or "1")))),
#     ("overall experience",    "years_of_experience", lambda p: str(int(float(p.get("years_of_experience") or "1")))),
#     ("linkedin",              "linkedin_url",        lambda p: p.get("linkedin_url") or ""),
#     ("github",                "github_url",          lambda p: p.get("github_url") or ""),
#     ("portfolio",             "portfolio_url",       lambda p: p.get("portfolio_url") or ""),
#     ("email",                 "email",               lambda p: p.get("email") or ""),
#     # Phone — specific phrases first to avoid matching "phone country code" select
#     ("mobile number",         "phone",               _extract_phone_digits),
#     ("mobile",                "phone",               _extract_phone_digits),
#     ("phone number",          "phone",               _extract_phone_digits),
#     ("phone",                 "phone",               _extract_phone_digits),
#     # Location — specific first
#     ("current city",          "current_city",        lambda p: p.get("current_city") or ""),
#     ("current location",      "current_city",        lambda p: p.get("current_city") or ""),
#     ("city",                  "current_city",        lambda p: p.get("current_city") or ""),
#     ("location",              "current_city",        lambda p: p.get("current_city") or ""),
# ]


# def _match_profile_field(label_lower: str, placeholder_lower: str, profile: dict) -> str | None:
#     """
#     Check whether an element label matches a known profile field.

#     Returns the profile value as a string (possibly empty string) if it's a profile
#     field, or None if it should be treated as a screening question.

#     Guards against false positives on "city" / "location" patterns:
#     If the label contains words that indicate it is a QUESTION about willingness /
#     comfort / preference rather than a plain data field, we skip the profile match
#     and send it to GPT instead.
#     """
#     combined = f"{label_lower} {placeholder_lower}"

#     # Words that signal the field is a screening question, not a data field.
#     # Applied only to the broad location/city patterns to avoid false matches like
#     # "Are you comfortable commuting to this job's location?" → city fill.
#     _LOCATION_QUESTION_SIGNALS = (
#         "comfortable", "commuting", "willing", "job's", "onsite",
#         "on-site", "work from", "preferred", "open to", "remote",
#         "relocat", "hybrid",
#     )

#     for phrase, _desc, extractor in _PROFILE_FIELD_PATTERNS:
#         if phrase not in combined:
#             continue

#         # For loose location/city keywords, verify this isn't a question
#         if phrase in ("location", "city", "current location", "current city"):
#             if any(sig in combined for sig in _LOCATION_QUESTION_SIGNALS):
#                 return None   # it's a screening question, send to GPT

#         try:
#             val = extractor(profile) if callable(extractor) else str(extractor)
#             return str(val) if val is not None else ""
#         except Exception:
#             return ""
#     return None


# def _values_match(current: str, expected: str) -> bool:
#     """
#     Return True if the DOM's current value already equals the expected profile value.
#     Handles: exact match, digit-only compare (salary/phone), substring (city in full address).
#     """
#     if not current or not expected:
#         return False
#     c = current.strip().lower()
#     e = expected.strip().lower()
#     if c == e:
#         return True
#     # Digit-only compare — handles salary formatting (8,00,000 vs 800000) and phone
#     c_d = re.sub(r"\D", "", c)
#     e_d = re.sub(r"\D", "", e)
#     if c_d and e_d:
#         if c_d == e_d:
#             return True
#         # Phone: compare last 10 digits
#         if len(c_d) >= 10 and len(e_d) >= 10 and c_d[-10:] == e_d[-10:]:
#             return True
#     # Substring: expected value contained in current (e.g. "Delhi" inside "Delhi, India")
#     if e and e in c:
#         return True
#     return False


# def _resolve_selector_from_elements(gpt_sel: str, elements: list) -> str | None:
#     """
#     Auto-correct a hallucinated GPT selector by word-overlap scoring against the
#     real element list.  Returns the best matching real selector, or None.

#     Used by both _batch_answer_page and _gpt_answer_screening so they share
#     identical correction logic without code duplication.
#     """
#     known = {e["selector"] for e in elements}
#     if gpt_sel in known:
#         return gpt_sel

#     # Strip CSS special chars to extract the semantic word(s)
#     # e.g. "#notice-period" → "notice period",  "[id='ember42']" → "id  ember42"
#     raw = re.sub(r"^[#.\['\"]", "", gpt_sel)
#     raw = re.sub(r"['\"\]]$", "", raw)
#     raw = re.sub(r"[-_]", " ", raw).lower().strip()
#     query_words = [w for w in raw.split() if len(w) >= 3]
#     if not query_words:
#         return None

#     best_sel, best_score = None, 0
#     for el in elements:
#         haystack = " ".join([
#             str(el.get("label", "")),
#             str(el.get("placeholder", "")),
#             str(el.get("name", "")),
#         ]).lower()
#         score = sum(1 for w in query_words if w in haystack)
#         if score > best_score:
#             best_score = score
#             best_sel = el["selector"]

#     return best_sel if best_score > 0 else None


# def _detect_page_type(page, elements: list) -> str:
#     """
#     Classify the current modal page so the main loop can take the fast path
#     without wasting a GPT call.

#     Returns
#     -------
#     "review"    — application summary / review page → just click Submit
#     "no_inputs" — page has no fillable fields → just click Next
#     "normal"    — regular form page with fields to fill
#     """
#     fillable_count = sum(
#         1 for e in elements
#         if e.get("tag") in ("input", "textarea", "select")
#         and e.get("type") not in ("hidden", "submit", "button", "file")
#     )
#     if fillable_count > 0:
#         return "normal"

#     # No fillable inputs — check whether it's a review/submit page
#     try:
#         body_lower = (page.inner_text("body") or "").lower()
#     except Exception:
#         body_lower = ""

#     _REVIEW_PHRASES = (
#         "review your application", "application summary",
#         "review application",      "application review",
#     )
#     if any(ph in body_lower for ph in _REVIEW_PHRASES):
#         return "review"

#     for sel in (
#         "button[aria-label='Submit application']",
#         "button:has-text('Submit application')",
#     ):
#         try:
#             btn = page.query_selector(sel)
#             if btn and btn.is_visible():
#                 return "review"
#         except Exception:
#             pass

#     return "no_inputs"


# def _gpt_answer_screening(elements: list, profile: dict) -> list[dict]:
#     """
#     Ask GPT to answer ONLY the screening questions that couldn't be answered from
#     the profile or session cache.

#     Sends resume + questions only — no full JD — to minimise token cost.
#     Returns a list of validated action dicts (never includes a "next" action).
#     """
#     if not elements:
#         return []

#     prompt = f"""You are filling LinkedIn Easy Apply screening questions for a candidate.

# === CANDIDATE RESUME ===
# {RESUME_TEXT[:1500]}

# === CANDIDATE QUICK PROFILE ===
# Experience       : {profile.get('years_of_experience', '1')} years total
# Skills           : {', '.join((profile.get('skills') or [])[:20])}
# Notice period    : {profile.get('notice_period', '30')} days
# City             : {profile.get('current_city', '')}
# Work auth India  : Yes
# Visa sponsorship : No

# === SCREENING QUESTIONS (answer only these) ===
# {json.dumps(elements, ensure_ascii=False)}

# Rules:
# - Return a JSON array — one action object per question that needs an answer.
# - Copy the "selector" field EXACTLY as it appears in the questions above. Never invent selectors.
# - VALID action types are ONLY: "fill", "click", "select", "typeahead".
#   NEVER use "input", "type", "write", or any other string — they are not valid and will break.
# - For text/number/textarea inputs (action="fill"): value is the text to type.
# - For <select> dropdowns (action="select"): value MUST exactly match one string from that element's options[].
# - For radio buttons (type="radio"): action="click", value = the option label text (e.g. "Yes", "No").
# - For numeric / years fields: return only the digit — no units, no surrounding text.
# - Authorization / work eligibility in India → "Yes".
# - Visa / sponsorship required → "No".
# - Skip elements whose currentValue is already correct.
# - Do NOT include a "next" action in your output.
# - Return ONLY a valid JSON array — no markdown, no code block, no explanation.
# """

#     try:
#         resp = _openai_client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "Return ONLY a valid JSON array. No markdown."},
#                 {"role": "user",   "content": prompt},
#             ],
#             response_format={"type": "json_object"},
#             max_tokens=800,
#             temperature=0,
#         )
#         _track_usage(resp)
#         raw  = resp.choices[0].message.content.strip()
#         data = json.loads(raw)

#         if isinstance(data, list):
#             actions = data
#         else:
#             actions = None
#             for key in ("actions", "steps", "result", "items"):
#                 if isinstance(data.get(key), list):
#                     actions = data[key]
#                     break

#         if not actions:
#             return []

#         # Validate & auto-correct selectors
#         known_sels = {e["selector"] for e in elements}
#         result: list[dict] = []
#         for act in actions:
#             if act.get("action") in ("next", "submit", "done"):
#                 continue
#             gpt_sel = str(act.get("selector", ""))
#             if gpt_sel and gpt_sel not in known_sels:
#                 corrected = _resolve_selector_from_elements(gpt_sel, elements)
#                 if corrected:
#                     print(f"     [screening] corrected: {gpt_sel!r} → {corrected!r}")
#                     act = {**act, "selector": corrected}
#                 else:
#                     print(f"     [screening] dropped hallucinated selector: {gpt_sel!r}")
#                     continue
#             result.append(act)

#         return result

#     except Exception as e:
#         print(f"     [screening] GPT call failed: {e}")
#         return []


# def _smart_fill_page(
#     page,
#     profile: dict,
#     elements: list,
#     job_title: str,
#     job_description: str,
# ) -> list[dict] | None:
#     """
#     Build an optimised action queue for one Easy Apply page.

#     Tier 1 — Profile fields  : answered directly from profile.json  (0 GPT tokens)
#     Tier 2 — Answer cache    : reuse answers seen in earlier jobs    (0 GPT tokens)
#     Tier 3 — GPT screening   : one batch call for the rest           (minimal tokens)

#     Special handling baked in:
#       • Multi-select checkbox groups (multiple checkboxes sharing one `name`) → skipped.
#       • Single consent / agreement checkboxes → auto-ticked.
#       • Phone country-code selects → filled with India (+91) from profile.
#       • Already-correct fields → skipped (verified against profile / cache).
#       • Number inputs → non-digit chars stripped before fill.
#     """
#     actions:    list[dict] = []
#     gpt_needed: list[dict] = []

#     # ── Detect multi-select checkbox groups ───────────────────────────────────
#     # Checkboxes sharing the same `name` attribute belong to a multi-select group.
#     name_counts: dict[str, int] = {}
#     for el in elements:
#         if el.get("type") == "checkbox":
#             n = el.get("name") or ""
#             if n:
#                 name_counts[n] = name_counts.get(n, 0) + 1
#     multi_select_names: set[str] = {n for n, c in name_counts.items() if c > 1}

#     for el in elements:
#         tag      = el.get("tag", "")
#         el_type  = el.get("type", "")
#         label    = el.get("label", "")
#         pholder  = el.get("placeholder", "")
#         selector = el.get("selector", "")
#         cur_val  = el.get("currentValue", "")
#         options  = el.get("options") or []
#         name     = el.get("name", "")
#         is_ta    = el.get("isTypeahead", False)
#         checked  = el.get("checked", False)

#         label_lo  = label.lower().strip()
#         phld_lo   = pholder.lower().strip()

#         # ── Non-fillable types ────────────────────────────────────────────────
#         if el_type in ("hidden", "submit", "button", "file"):
#             continue
#         if tag in ("button", "label"):
#             # <label> elements are returned by _modal_elements for navigation but
#             # cannot be filled — filling them throws "Illegal invocation".
#             continue

#         # ── Follow-company checkbox — always skip ─────────────────────────────
#         if el_type == "checkbox" and "follow" in label_lo:
#             continue

#         # ── Multi-select checkbox group — skip ────────────────────────────────
#         if el_type == "checkbox" and name and name in multi_select_names:
#             _log(f"     [smart] Multi-select skip: {label[:60]}", "info")
#             continue

#         # ── Consent / agreement single checkbox — auto-tick ───────────────────
#         if el_type == "checkbox":
#             _CONSENT = ("agree", "consent", "terms", "certify", "confirm",
#                         "declare", "acknowledge", "accept", "authoriz", "policy")
#             if any(kw in label_lo for kw in _CONSENT):
#                 if not checked:
#                     actions.append({
#                         "action":   "click",
#                         "selector": selector,
#                         "value":    "",
#                         "reason":   f"Consent: {label[:50]}",
#                     })
#                 continue   # handled regardless of prior state

#         # ── Phone country-code select → India (+91) ───────────────────────────
#         if tag == "select":
#             is_cc = (
#                 ("country" in label_lo and "code" in label_lo) or
#                 ("phone"   in label_lo and "country" in label_lo) or
#                 any(str(o).strip().startswith("+") for o in options[:5])
#             )
#             if is_cc:
#                 india_opt = next(
#                     (o for o in options if "india" in str(o).lower() or "+91" in str(o)),
#                     "+91 India",
#                 )
#                 if "india" in cur_val.lower() or "+91" in cur_val:
#                     continue   # already correct
#                 actions.append({
#                     "action":   "select",
#                     "selector": selector,
#                     "value":    india_opt,
#                     "reason":   "Phone country code → India (+91)",
#                 })
#                 continue

#         # ── Tier 1: Profile field ─────────────────────────────────────────────
#         profile_val = _match_profile_field(label_lo, phld_lo, profile)
#         if profile_val is not None:
#             if not profile_val:
#                 continue    # profile has no value for this field — skip silently

#             if _values_match(cur_val, profile_val):
#                 _log(f"     [smart] T1-skip (already filled): {label[:50]}", "info")
#                 continue

#             _log(f"     [smart] T1-fill: {label[:50]} → {profile_val[:30]}", "info")

#             if tag == "select":
#                 actions.append({"action": "select",    "selector": selector, "value": profile_val, "reason": f"Profile: {label[:40]}"})
#             elif is_ta:
#                 actions.append({"action": "typeahead", "selector": selector, "value": profile_val, "reason": f"Profile: {label[:40]}"})
#             else:
#                 fill_val = profile_val
#                 if el_type == "number" or "numeric" in selector.lower():
#                     fill_val = re.sub(r"[^\d.]", "", fill_val) or fill_val
#                 actions.append({"action": "fill", "selector": selector, "value": fill_val, "reason": f"Profile: {label[:40]}"})
#             continue

#         # ── Tier 2: Answer cache ──────────────────────────────────────────────
#         cache_key = _normalize_cache_key(label or pholder)
#         if cache_key and cache_key in _answer_cache:
#             cached = _answer_cache[cache_key]
#             if _values_match(cur_val, cached):
#                 _log(f"     [smart] T2-skip (cache match): {label[:50]}", "info")
#                 continue

#             _log(f"     [smart] T2-fill (cached): {label[:50]} → {cached[:30]}", "info")
#             act_type = (
#                 "select" if tag == "select" else
#                 "click"  if el_type == "radio" else
#                 "fill"
#             )
#             actions.append({"action": act_type, "selector": selector, "value": cached, "reason": f"Cached: {label[:40]}"})
#             continue

#         # ── Tier 3: Needs GPT ─────────────────────────────────────────────────
#         if tag in ("input", "textarea", "select") or el_type == "radio":
#             gpt_needed.append(el)

#     # ── One GPT call for all remaining screening questions ────────────────────
#     if gpt_needed:
#         _log(f"     [smart] T3-GPT: {len(gpt_needed)} screening question(s)", "info")
#         gpt_actions = _gpt_answer_screening(gpt_needed, profile)

#         # Cache non-sensitive GPT answers for future jobs in this session
#         _NO_CACHE = ("salary", "ctc", "compensation", "pay", "notice", "expected", "current")
#         for act in gpt_actions:
#             gpt_sel = act.get("selector", "")
#             gpt_val = act.get("value", "")
#             if gpt_val:
#                 for src_el in gpt_needed:
#                     if src_el.get("selector") == gpt_sel:
#                         el_label = src_el.get("label") or src_el.get("placeholder", "")
#                         ck = _normalize_cache_key(el_label)
#                         if ck and not any(kw in el_label.lower() for kw in _NO_CACHE):
#                             _answer_cache[ck] = gpt_val
#                         break
#             actions.append(act)

#     if not actions and not gpt_needed:
#         return None   # nothing to do — caller handles Next click

#     # Terminate queue with a navigation action
#     actions.append({"action": "next", "selector": "", "value": "", "reason": "All fields processed"})
#     return actions


# _BATCH_SYSTEM = """You are an expert job application AI. You see ALL the questions on one page of a LinkedIn Easy Apply form.
# Your job: return a JSON array of actions that fills EVERY required field on this page optimally for this specific role.

# CRITICAL RULES:
# - Read the JOB DESCRIPTION carefully. Tailor every answer to impress the hiring manager for THIS specific role.
# - For "years of experience" fields: return a whole integer. Check the resume for the specific skill.
#   If the skill is on the resume → use actual years. If not → return 0 (be honest, don't inflate).
# - For YES/NO questions about skills in the JD: answer YES if the resume shows even adjacent/transferable experience.
# - For notice period: always use the candidate's actual notice period in days.
# - For salary: use the candidate's CTC values exactly.
# - For demographic/optional fields: "Prefer not to say" or "Decline to self-identify".
# - Skip "Follow company" checkboxes entirely (do not include them in output).
# - End the array with {"action":"next","selector":"","value":"","reason":"All fields filled"}.

# SELECTOR RULES (MOST IMPORTANT):
# - The "selector" field in EVERY action MUST be copied EXACTLY and VERBATIM from the "selector" key in the FORM ELEMENTS JSON you receive.
# - NEVER invent, shorten, simplify, or rewrite a selector. Do NOT use #email, #phone, #city, #name, or any other shorthand — these do not exist in LinkedIn's DOM.
# - LinkedIn uses non-semantic IDs like [id='ember342'] or [id='urn:li:...'] — always copy them exactly as given.
# - If you cannot find a matching selector in the FORM ELEMENTS list for a field, simply omit that field from your output rather than guessing.

# Return ONLY a valid JSON array — no markdown, no code block, no explanation.
# Each element: {"action":"fill"|"typeahead"|"click"|"select","selector":"EXACT selector from FORM ELEMENTS list","value":"answer","reason":"why"}
# """


# def _batch_answer_page(page, profile: dict, job_title: str,
#                        job_description: str, elements: list) -> list[dict] | None:
#     """
#     Ask GPT to answer ALL questions on this page in ONE call with full JD context.
#     Returns a list of action dicts (ending with "next"), or None on failure.
#     This is smarter and cheaper than per-field calls because GPT sees the full picture.
#     """
#     # Only batch if there are actual form fields to fill
#     fillable = [
#         e for e in elements
#         if e.get("tag") in ("input", "textarea", "select")
#         and e.get("type") not in ("hidden", "submit", "button", "file")
#     ]
#     if not fillable:
#         return None

#     name_parts   = profile.get("full_name", "").split()
#     first_name   = name_parts[0] if name_parts else ""
#     last_name    = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
#     phone_raw    = re.sub(r"\D", "", profile.get("phone", ""))
#     phone_digits = phone_raw[-10:] if len(phone_raw) >= 10 else phone_raw
#     try:
#         exp_int = str(max(1, int(float(profile.get("years_of_experience", "1") or "1"))))
#     except Exception:
#         exp_int = "1"

#     prompt = f"""You are filling a LinkedIn Easy Apply form for:
# Role: {job_title}

# === JOB DESCRIPTION ===
# {job_description[:3000]}

# === CANDIDATE PROFILE ===
# Full name: {profile.get('full_name', '')}
# First: {first_name}  Last: {last_name}
# Email: {profile.get('email', '')}
# Phone (digits only): {phone_digits}
# City: {profile.get('current_city', '')}
# Current role: {profile.get('current_job_title', '')} at {profile.get('current_company', '')}
# Total experience: {exp_int} years
# Skills: {', '.join(profile.get('skills', [])[:25])}
# Notice period: {profile.get('notice_period', '30')} days
# Current CTC: {profile.get('current_salary', '')}
# Expected CTC: {profile.get('expected_salary', '')}
# LinkedIn: {profile.get('linkedin_url', '')}
# GitHub: {profile.get('github_url', '')}

# === RESUME (first 1200 chars) ===
# {RESUME_TEXT[:1200]}

# === FORM ELEMENTS (ALL questions on this page) ===
# {json.dumps(fillable, ensure_ascii=False)}

# Instructions:
# - Answer EVERY element above that is empty or needs a value.
# - Tailor answers to make the candidate look ideal for THIS specific role.
# - For skills mentioned in the JD that are also in the resume → give positive/experienced answers.
# - For skills NOT in the resume → answer honestly (0 years, No, etc.).
# - Elements with a non-empty currentValue that looks correct → skip them (don't include in output).
# - End with the "next" action.
# """

#     try:
#         resp = _openai_client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": _BATCH_SYSTEM},
#                 {"role": "user",   "content": prompt},
#             ],
#             response_format={"type": "json_object"},
#             max_tokens=1500,
#             temperature=0,
#         )
#         _track_usage(resp)
#         raw = resp.choices[0].message.content.strip()

#         # ── Robust JSON parsing with truncation recovery ──────────────────
#         # If GPT hit the token limit mid-response the JSON is truncated.
#         # Try to salvage the actions already written before the cut-off.
#         parsed = None
#         try:
#             parsed = json.loads(raw)
#         except json.JSONDecodeError:
#             # Attempt to extract the partial array before truncation
#             try:
#                 # Find last complete object ending with }
#                 last_close = raw.rfind("},")
#                 if last_close == -1:
#                     last_close = raw.rfind("}")
#                 if last_close > 0:
#                     partial = raw[:last_close + 1]
#                     # Wrap into a valid array
#                     bracket = partial.find("[")
#                     if bracket != -1:
#                         partial = partial[bracket:] + "]"
#                     else:
#                         partial = "[" + partial + "]"
#                     actions_partial = json.loads(partial)
#                     # Append a "next" action so the partial batch still terminates cleanly
#                     actions_partial.append(
#                         {"action": "next", "selector": "", "value": "",
#                          "reason": "Recovered from truncated batch response"}
#                     )
#                     print(f"     [batch] Recovered {len(actions_partial)-1} actions from truncated JSON")
#                     return actions_partial
#             except Exception:
#                 pass
#             print(f"     [batch] GPT batch call failed: {e}")
#             return None

#         if isinstance(parsed, list):
#             actions = parsed
#         else:
#             actions = None
#             for key in ("actions", "steps", "result", "items"):
#                 if key in parsed and isinstance(parsed[key], list):
#                     actions = parsed[key]
#                     break

#         if actions is None:
#             return None

#         # ── Selector auto-correction ──────────────────────────────────────────
#         # Delegate to the shared module-level helper so the logic is identical
#         # across _batch_answer_page, _gpt_answer_screening, and any future callers.
#         validated: list[dict] = []
#         for act in actions:
#             if act.get("action") in ("next", "submit"):
#                 validated.append(act)
#                 continue

#             gpt_sel  = str(act.get("selector", ""))
#             resolved = _resolve_selector_from_elements(gpt_sel, fillable)

#             if resolved is None:
#                 print(f"     [batch] dropped hallucinated selector: {gpt_sel!r} (no match in DOM)")
#                 continue

#             if resolved != gpt_sel:
#                 print(f"     [batch] corrected selector: {gpt_sel!r} → {resolved!r}")
#                 act = {**act, "selector": resolved}

#             validated.append(act)

#         return validated if validated else None

#     except Exception as e:
#         print(f"     [batch] GPT batch call failed: {e}")
#         return None


# def handle_easy_apply_modal(page, profile: dict,
#                              job_title: str = "", job_description: str = "") -> str:
#     """
#     LinkedIn Easy Apply — vision-driven multi-step filler.

#     Each step:
#       1. Screenshot the modal
#       2. Ask GPT what to fill or click
#       3. Execute the action
#       4. On failure: retry with error context (max 3 failures per action)
#       5. When GPT returns "next": click the navigation button
#       6. Stop on success toast or after max steps
#     """
#     name_parts   = profile.get("full_name", "").split()
#     first_name   = name_parts[0] if name_parts else ""
#     last_name    = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
#     phone_raw    = re.sub(r"\D", "", profile.get("phone", ""))
#     phone_digits = phone_raw[-10:] if len(phone_raw) >= 10 else phone_raw

#     tried:                  dict[tuple, int] = {}   # (act, sel, val) → failure count only
#     action_counts:          dict[tuple, int] = {}   # loop guard
#     last_error:             str              = ""
#     consecutive_fails:      int              = 0
#     consecutive_next:       int              = 0    # how many times "next" was clicked in a row
#     resume_handled_count:   int              = 0   # guard against infinite resume-page loops
#     MAX_STEPS                               = 50
#     MAX_CONSEC                              = 3

#     # Per-page batch action queue:
#     # When we land on a NEW page (after "next"), call _batch_answer_page once to
#     # get ALL actions for that page in one JD-aware GPT call.  We then execute
#     # them from the queue.  If a queued action fails we fall back to per-step GPT.
#     page_action_queue: list[dict] = []
#     last_page_fingerprint: str   = ""   # tracks which page the queue was built for

#     for step in range(1, MAX_STEPS + 1):

#         if _modal_is_success(page):
#             _log("     [modal] Application submitted!", "success")
#             _screenshot(page)
#             return "applied"

#         # ── Resume selection fast-path — no GPT needed ────────────────────────
#         if _handle_resume_selection(page, profile):
#             resume_handled_count += 1
#             _log(f"     [modal] Resume selection handled ({resume_handled_count}×)", "info")
#             if resume_handled_count > 3:
#                 _log("     [modal] Resume selection page stuck — skipping job", "warning")
#                 return "skipped"
#             tried.clear()
#             action_counts.clear()
#             last_error = ""
#             consecutive_fails = 0
#             page_action_queue.clear()
#             continue

#         # Check modal still open
#         modal = page.query_selector(".jobs-easy-apply-content, [role='dialog']")
#         if not modal:
#             _log("     [modal] Modal closed", "info")
#             break

#         elements = _modal_elements(page)

#         # ── Page type fast-path ───────────────────────────────────────────────
#         # Detect review/summary pages and no-input pages before any GPT call.
#         page_type = _detect_page_type(page, elements)
#         if page_type in ("review", "no_inputs"):
#             _log(
#                 f"     [modal] {'Review/submit' if page_type == 'review' else 'No-input'} "
#                 f"page — clicking Next/Submit directly",
#                 "info",
#             )
#             _modal_click_next(page)
#             time.sleep(2.5)
#             page_action_queue.clear()
#             last_page_fingerprint = ""
#             consecutive_next += 1
#             if consecutive_next >= 5:
#                 _log("     [modal] Stuck in no-input loop — skipping job", "warning")
#                 return "skipped"
#             continue

#         # Real page with fillable fields — reset no-input counter
#         consecutive_next = 0

#         # ── Compute page fingerprint to detect when we land on a NEW page ─────
#         current_fp = "|".join(
#             e.get("selector", "")[:40] + e.get("label", "")[:20]
#             for e in elements
#         )

#         # If the page changed (navigation happened), rebuild the action queue
#         if current_fp != last_page_fingerprint and not last_error:
#             last_page_fingerprint = current_fp

#             # ── Smart fill: Tier 1 (profile) → Tier 2 (cache) → Tier 3 (GPT) ──
#             if consecutive_fails == 0:
#                 batch = _smart_fill_page(
#                     page, profile, elements, job_title, job_description
#                 )
#                 if batch:
#                     page_action_queue = batch
#                     _log(
#                         f"     [modal] Smart fill: {len(batch)} actions for this page "
#                         f"(T1/T2 = no-GPT, T3 = screening only)",
#                         "info",
#                     )

#         # ── Pull next action from queue (if available and not in recovery mode) ─
#         if page_action_queue and consecutive_fails == 0 and not last_error:
#             action = page_action_queue.pop(0)
#             act    = (action.get("action") or "").strip()
#             sel    = (action.get("selector") or "").strip()
#             val    = (action.get("value") or "").strip()
#             reason = (action.get("reason") or "")
#             _log(
#                 f"     [modal] Step {step} [batch]: {act} | {sel[:70]} | {val[:40]} — {reason}",
#                 "info",
#             )
#             _screenshot(page)

#             # Handle terminal batch actions inline
#             if act == "done":
#                 if _modal_is_success(page):
#                     return "applied"
#                 return "applied"

#             if act == "next":
#                 # Skip the nav action from the queue — let the main next-handler do it
#                 # by putting "next" back and falling through to the per-step GPT path
#                 # Actually: just execute it directly here
#                 pre_fp = current_fp
#                 clicked = _modal_click_next(page)
#                 if clicked:
#                     _log(f"     [modal] [batch] Navigation button clicked", "info")
#                     time.sleep(2.5)
#                     post_els = _modal_elements(page)
#                     post_fp = "|".join(
#                         e.get("selector", "")[:40] + e.get("label", "")[:20]
#                         for e in post_els
#                     )
#                     if post_fp != pre_fp or _modal_is_success(page):
#                         tried.clear()
#                         action_counts.clear()
#                         last_error = ""
#                         consecutive_fails = 0
#                         page_action_queue.clear()   # old queue is for old page
#                     else:
#                         consecutive_next += 1
#                         page_action_queue.clear()
#                         last_error = (
#                             "Next was clicked but the page did NOT advance. "
#                             "Look for unfilled required fields or validation errors."
#                         )
#                         consecutive_fails = 2   # force vision on next fallback step
#                         if consecutive_next >= 5:
#                             return "skipped"
#                 continue

#             # Execute the queued action (non-nav)
#             if act == "upload_resume":
#                 ok, error = _modal_execute(page, profile, action)
#                 if not ok:
#                     # Upload failure: skip this action, keep rest of queue
#                     _log(f"     [modal] Batch upload failed: {error} — skipping", "warning")
#                 continue

#             # Skip follow-company
#             if act == "click" and "follow" in sel.lower():
#                 continue

#             # ── Validate selector exists in DOM before executing ──────────────
#             # Batch GPT sometimes hallucinates IDs that don't exist. Check first
#             # so a bad selector doesn't abort the whole queue.
#             if sel:
#                 known_selectors = [e.get("selector", "") for e in elements]
#                 sel_known = (
#                     sel in known_selectors or
#                     any(sel[:50] in ks or ks[:50] in sel for ks in known_selectors)
#                 )
#                 if not sel_known:
#                     # Selector not in DOM — skip this queued action silently
#                     _log(
#                         f"     [modal] Batch selector not in DOM, skipping: {sel[:60]}",
#                         "warning",
#                     )
#                     continue

#             # Execute field action
#             _human_delay(150, 450)
#             target_label = ""
#             try:
#                 for _el in elements:
#                     if _el.get("selector", "") == sel or sel[:40] in _el.get("selector", ""):
#                         target_label = _el.get("label", "")[:50]
#                         break
#             except Exception:
#                 pass

#             ok, error = _modal_execute(page, profile, action)

#             if ok:
#                 consecutive_fails = 0
#                 last_error = ""
#                 _human_delay(250, 600)
#                 loop_key = (act, sel, val, target_label)
#                 action_counts[loop_key] = action_counts.get(loop_key, 0) + 1
#                 if action_counts[loop_key] >= 4:
#                     _log(f"     [modal] Loop guard fired on batch action — falling back to per-step", "warning")
#                     page_action_queue.clear()
#                     action_counts.clear()
#             else:
#                 # Single batch action failed — skip it, keep the rest of the queue.
#                 # Only abort the queue after 3 consecutive batch failures.
#                 consecutive_fails += 1
#                 _log(
#                     f"     [modal] Batch action FAILED ({consecutive_fails}×): {error} — skipping action",
#                     "warning",
#                 )
#                 tried[(act, sel, val)] = tried.get((act, sel, val), 0) + 1
#                 if consecutive_fails >= MAX_CONSEC:
#                     _log(
#                         f"     [modal] {MAX_CONSEC} consecutive batch failures — switching to per-step GPT",
#                         "warning",
#                     )
#                     page_action_queue.clear()
#                     last_error = error
#                     consecutive_fails = 0   # reset so per-step starts clean

#             continue

#         # ── Per-step GPT fallback (also used when queue is empty or in error recovery) ─
#         elements_json = json.dumps(elements, ensure_ascii=False)

#         error_note = (
#             f"\n⚠ Last action FAILED: {last_error}\nTry a different selector or method.\n"
#             if last_error else ""
#         )
#         tried_note = ""
#         if tried:
#             lines = "\n".join(
#                 f"  - action={a!r} selector={s!r} value={v!r} (tried {c}×)"
#                 for (a, s, v), c in tried.items()
#             )
#             tried_note = f"\nAlready tried — do NOT repeat any of these (even if they 'succeeded'):\n{lines}\n"

#         # Integer experience for LLM (never decimal — LinkedIn numeric fields require integers)
#         try:
#             exp_int = str(max(1, int(float(profile.get("years_of_experience", "1") or "1"))))
#         except Exception:
#             exp_int = "1"

#         jd_snippet = ""
#         if job_description:
#             jd_snippet = f"\nJob being applied for: {job_title}\nJD summary:\n{job_description[:1500]}\n"

#         candidate_text = (
#             f"Step {step}/{MAX_STEPS}\n\n"
#             f"Candidate profile:\n"
#             f"  Full name          : {profile.get('full_name', '')}\n"
#             f"  First name         : {first_name}\n"
#             f"  Last name          : {last_name}\n"
#             f"  Email              : {profile.get('email', '')}\n"
#             f"  Phone digits       : {phone_digits}  ← ONLY these digits, no country code\n"
#             f"  City               : {profile.get('current_city', '')}\n"
#             f"  Job title          : {profile.get('current_job_title', '')}\n"
#             f"  Current company    : {profile.get('current_company', '')}\n"
#             f"  Total experience   : {exp_int} years  ← USE THIS INTEGER for any 'years of experience' field\n"
#             f"  Skills             : {', '.join(profile.get('skills', [])[:20])}\n"
#             f"  Notice period      : {profile.get('notice_period', '30')} days\n"
#             f"  Current CTC        : {profile.get('current_salary', '')}\n"
#             f"  Expected CTC       : {profile.get('expected_salary', '')}\n"
#             f"  LinkedIn URL       : {profile.get('linkedin_url', '')}\n"
#             f"  GitHub URL         : {profile.get('github_url', '')}\n"
#             f"  Employed           : Yes\n"
#             f"  Sponsorship needed : No\n"
#             f"  Work authorized    : Yes\n\n"
#             f"Resume text (first 1000 chars):\n{RESUME_TEXT[:1000]}\n"
#             f"{jd_snippet}"
#             f"{error_note}"
#             f"{tried_note}\n"
#             f"IMPORTANT: Each element below has a 'currentValue' field showing what is already filled.\n"
#             f"If currentValue is correct, SKIP that field and move to the next empty required one.\n\n"
#             f"Modal elements (DOM):\n{elements_json}"
#         )

#         # ── Step 1: DOM-only call (no vision — cheaper) ───────────────────────
#         # ── Step 2: Vision fallback if stuck (2+ consecutive failures) ────────
#         use_vision = consecutive_fails >= 2
#         if use_vision:
#             screenshot_b64 = _modal_screenshot_b64(page)
#             user_content: list | str = [
#                 {
#                     "type": "image_url",
#                     "image_url": {
#                         "url":    f"data:image/jpeg;base64,{screenshot_b64}",
#                         "detail": "high",
#                     },
#                 },
#                 {"type": "text", "text": candidate_text},
#             ]
#             _log(f"     [modal] Step {step}: using vision fallback (stuck)", "warning")
#         else:
#             user_content = candidate_text

#         try:
#             resp = _openai_client.chat.completions.create(
#                 model="gpt-4o-mini",
#                 messages=[
#                     {"role": "system", "content": _MODAL_VISION_SYSTEM},
#                     {"role": "user",   "content": user_content},
#                 ],
#                 response_format={"type": "json_object"},
#                 max_tokens=200,
#                 temperature=0,
#             )
#             _track_usage(resp)
#             action = json.loads(resp.choices[0].message.content.strip())
#         except Exception as e:
#             err_str = str(e)
#             if "429" in err_str or "rate limit" in err_str.lower():
#                 wait_sec = 2.0
#                 ms_match = re.search(r"try again in (\d+)ms", err_str, re.IGNORECASE)
#                 s_match  = re.search(r"try again in ([\d.]+)s", err_str, re.IGNORECASE)
#                 if ms_match:
#                     wait_sec = max(1.0, int(ms_match.group(1)) / 1000 + 0.5)
#                 elif s_match:
#                     wait_sec = max(1.0, float(s_match.group(1)) + 0.5)
#                 _log(f"     [modal] Rate limited — waiting {wait_sec:.1f}s before retry", "warning")
#                 time.sleep(wait_sec)
#                 continue  # Don't count as a failure
#             _log(f"     [modal] GPT error at step {step}: {e}", "warning")
#             consecutive_fails += 1
#             if consecutive_fails >= MAX_CONSEC:
#                 break
#             continue

#         act    = (action.get("action") or "").strip()
#         sel    = (action.get("selector") or "").strip()
#         val    = (action.get("value") or "").strip()
#         reason = (action.get("reason") or "")

#         _log(f"     [modal] Step {step}: {act} | {sel[:70]} | {val[:40]}  — {reason}", "info")
#         _screenshot(page)

#         # ── Terminal: submit / next / done ───────────────────────────────────────
#         if act == "done":
#             if _modal_is_success(page):
#                 return "applied"
#             # Treat as applied if GPT is confident
#             return "applied"

#         if act == "next":
#             # Snapshot page selector fingerprint before clicking so we can tell
#             # whether the page actually advanced after the click.
#             pre_fingerprint = ""
#             try:
#                 pre_els = _modal_elements(page)
#                 pre_fingerprint = "|".join(
#                     e.get("selector", "") + e.get("label", "")[:30]
#                     for e in pre_els
#                 )
#             except Exception:
#                 pass

#             clicked = _modal_click_next(page)
#             if clicked:
#                 _log(f"     [modal] Navigation button clicked", "info")
#                 time.sleep(2.5)

#                 # Check whether the page actually changed
#                 post_fingerprint = ""
#                 try:
#                     post_els = _modal_elements(page)
#                     post_fingerprint = "|".join(
#                         e.get("selector", "") + e.get("label", "")[:30]
#                         for e in post_els
#                     )
#                 except Exception:
#                     pass

#                 page_advanced = (post_fingerprint != pre_fingerprint) or _modal_is_success(page)

#                 if page_advanced:
#                     # Real advance — reset all state
#                     tried.clear()
#                     action_counts.clear()
#                     last_error = ""
#                     consecutive_fails = 0
#                     consecutive_next = 0
#                 else:
#                     # Button clicked but page didn't move — collect any error text
#                     consecutive_next += 1
#                     error_texts: list[str] = []
#                     try:
#                         err_els = page.query_selector_all(
#                             ".artdeco-inline-feedback--error, "
#                             ".fb-form-element__error-field, "
#                             "[data-test-inline-error]"
#                         )
#                         error_texts = [
#                             (el.inner_text() or "").strip()
#                             for el in err_els
#                             if el.is_visible() and (el.inner_text() or "").strip()
#                         ]
#                     except Exception:
#                         pass

#                     if error_texts:
#                         last_error = (
#                             f"Next clicked but form has validation errors: "
#                             f"{'; '.join(error_texts[:5])}. Fix these errors first."
#                         )
#                     else:
#                         last_error = (
#                             "Next was clicked but the page did NOT advance. "
#                             "Look for: (1) unfilled required fields, "
#                             "(2) unchecked agreement/consent checkboxes, "
#                             "(3) a 'Follow company' checkbox that must be ticked, "
#                             "(4) a radio button group with no selection. "
#                             "Fill or click whatever is blocking submission."
#                         )

#                     # Force vision on next call so LLM can actually see the page
#                     consecutive_fails = 2

#                     if consecutive_next >= 5:
#                         _log(
#                             f"     [modal] Stuck in next-click loop "
#                             f"({consecutive_next}×) — skipping job",
#                             "warning",
#                         )
#                         try:
#                             page.locator("button[aria-label='Dismiss']").first.click()
#                         except Exception:
#                             pass
#                         return "skipped"

#             else:
#                 _log(f"     [modal] No nav button found on step {step}", "warning")
#                 consecutive_next = 0
#                 consecutive_fails += 1
#                 if consecutive_fails >= MAX_CONSEC:
#                     break
#             continue

#         if act == "upload_resume":
#             ok, error = _modal_execute(page, profile, action)
#             if ok:
#                 consecutive_fails = 0
#                 last_error = ""
#                 time.sleep(1)
#             else:
#                 last_error = error
#                 consecutive_fails += 1
#             continue

#         # ── Auto-skip "Follow company" checkbox — never block on it ─────────────
#         if act == "click" and "follow" in sel.lower():
#             _log(f"     [modal] Auto-skipping follow-company checkbox", "info")
#             continue
#         # Also skip if the label text says "follow"
#         follow_label = (action.get("reason") or "").lower()
#         if act == "click" and "follow" in follow_label and "company" in follow_label:
#             _log(f"     [modal] Auto-skipping follow-company click", "info")
#             continue

#         # ── Regular field action ─────────────────────────────────────────────────
#         consecutive_next = 0   # a real action broke the next-click chain
#         _human_delay(150, 500)   # human-like pause before each action

#         # Get the label of the target element BEFORE executing the action.
#         # LinkedIn reuses the SAME selector for multiple sequential questions —
#         # only the label changes.  Including label in the loop key means
#         # ("fill", sel, "0", "Program design years") and
#         # ("fill", sel, "0", "Women empowerment years") are separate counters,
#         # so filling "0" for many different questions never triggers a false skip.
#         target_label = ""
#         try:
#             cur_els = _modal_elements(page)
#             for _el in cur_els:
#                 if _el.get("selector", "") == sel:
#                     target_label = _el.get("label", "")[:50]
#                     break
#                 # Partial match for truncated IDs
#                 if sel and sel[:40] in _el.get("selector", ""):
#                     target_label = _el.get("label", "")[:50]
#         except Exception:
#             pass

#         ok, error = _modal_execute(page, profile, action)
#         fail_key = (act, sel, val)   # failure counter key

#         if ok:
#             consecutive_fails = 0
#             last_error = ""
#             _human_delay(300, 700)   # human-like pause after successful action

#             # Loop key includes label so different questions on the same element
#             # are never conflated, even when selector and value are identical.
#             loop_key = (act, sel, val, target_label)
#             action_counts[loop_key] = action_counts.get(loop_key, 0) + 1
#             if action_counts[loop_key] >= 4:
#                 _log(
#                     f"     [modal] '{act}' on '{sel[:60]}' label='{target_label[:30]}' "
#                     f"(val='{val}') repeated 4× with no advance — skipping job",
#                     "warning",
#                 )
#                 try:
#                     page.locator("button[aria-label='Dismiss']").first.click()
#                 except Exception:
#                     pass
#                 return "skipped"

#         else:
#             # Only failed attempts count toward the skip threshold
#             tried[fail_key] = tried.get(fail_key, 0) + 1
#             last_error = error
#             consecutive_fails += 1

#             _log(f"     [modal] Step {step} FAILED ({tried[fail_key]}×): {error}", "warning")

#             if tried[fail_key] >= MAX_CONSEC:
#                 # This specific action has failed MAX_CONSEC times.
#                 # If the error is a timeout / element-not-found (element disappeared
#                 # from DOM after being answered or after navigation), abandon ONLY
#                 # this action and let GPT pick the next thing to do.
#                 # Only skip the entire job if nothing at all is advancing
#                 # (consecutive_fails guard below handles that).
#                 is_gone = any(kw in error.lower() for kw in (
#                     "timeout", "not visible", "not found", "detached",
#                     "element is not attached", "exceeded",
#                 ))
#                 if is_gone:
#                     _log(
#                         f"     [modal] Element gone/not visible after {MAX_CONSEC} tries — "
#                         f"abandoning this action, continuing",
#                         "warning",
#                     )
#                     # Don't reset consecutive_fails so vision activates on next step
#                 else:
#                     _log(f"     [modal] Action failed {MAX_CONSEC}× — skipping job", "warning")
#                     try:
#                         page.locator("button[aria-label='Dismiss']").first.click()
#                     except Exception:
#                         pass
#                     return "skipped"

#             if consecutive_fails >= MAX_CONSEC:
#                 _log(f"     [modal] {MAX_CONSEC} consecutive failures — skipping job", "warning")
#                 try:
#                     page.locator("button[aria-label='Dismiss']").first.click()
#                 except Exception:
#                     pass
#                 return "skipped"

#     # Close modal if still open
#     try:
#         page.locator("button[aria-label='Dismiss']").first.click()
#     except Exception:
#         pass

#     return "skipped"


# ###  old helpers removed — vision loop handles everything  ###
# # ---------------------------------------------------------------------------
# # Per-job apply — START (scroll down)


# # ---------------------------------------------------------------------------
# # Per-job apply
# # ---------------------------------------------------------------------------

# def get_job_description(page) -> str:
#     """Extract full job description text from the current job page."""
#     for sel in [
#         ".jobs-description-content__text",
#         ".jobs-description__content",
#         ".job-details-jobs-unified-top-card__job-insight",
#         "#job-details",
#         ".description__text",
#     ]:
#         try:
#             el = page.query_selector(sel)
#             if el:
#                 txt = el.inner_text().strip()
#                 if len(txt) > 100:
#                     return txt
#         except Exception:
#             continue
#     # Fallback: grab all visible paragraph text
#     try:
#         return page.evaluate("""
#             () => Array.from(document.querySelectorAll('p, li'))
#                        .map(e => e.innerText.trim())
#                        .filter(t => t.length > 20)
#                        .join('\\n')
#         """)
#     except Exception:
#         return ""


# def is_good_fit(job: dict, description: str) -> tuple[bool, str]:
#     """
#     Decide whether to apply to a job.

#     Decision hierarchy
#     ──────────────────
#     1. Fast path — if the job title contains any keyword from the user's
#        search query, always apply.  The user explicitly said they want this
#        role; we must not override that intent.
#     2. Slow path (GPT) — for titles that don't match the query, estimate the
#        candidate's skill overlap with the JD.  Skip ONLY when overlap < 30 %.
#        All other reasons (seniority, category, etc.) are ignored.
#     """
#     # ── Fast path: title matches the user's search query ─────────────────────
#     # Split on commas, pipes, slashes and spaces so "AIML Engineer, Data Scientist"
#     # becomes ["AIML", "Engineer", "Data", "Scientist"].
#     query_terms = [
#         t.strip().lower()
#         for t in re.split(r"[,|/\s]+", JOB_SEARCH_QUERY)
#         if len(t.strip()) > 2
#     ]
#     title_lower = job["title"].lower()
#     matching = [t for t in query_terms if t in title_lower]
#     if matching:
#         return True, f"Title matches your search query ('{', '.join(matching)}')"

#     # ── Slow path: GPT skill-overlap check ───────────────────────────────────
#     prompt = f"""You are a recruiter screening a job application.

# The user is searching for: "{JOB_SEARCH_QUERY}"

# Candidate's resume summary:
# {RESUME_TEXT[:1500]}

# Job Title   : {job['title']}
# Company     : {job['company']}
# Description : {description[:2000]}

# Your only task: estimate what percentage of the job's REQUIRED skills the
# candidate already has based on their resume.

# Rules — apply strictly in order:
# 1. Count only skills the JD lists as required or strongly preferred.
# 2. A skill counts if the candidate's resume shows it or a close equivalent.
# 3. SKIP (NO) only if the candidate has fewer than 30 % of required skills.
# 4. For ALL other cases return YES — do NOT reject on title, seniority, or
#    role category. The user chose this search query deliberately.

# Reply in exactly this format (2 lines, nothing else):
# DECISION: YES or NO
# REASON: one sentence — state the approximate skill overlap percentage
# """
#     try:
#         resp = _openai_client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0,
#             max_tokens=80,
#         )
#         _track_usage(resp)
#         text = resp.choices[0].message.content.strip()
#         decision = "YES" in text.split("\n")[0].upper()
#         reason = ""
#         for line in text.split("\n"):
#             if line.upper().startswith("REASON:"):
#                 reason = line.split(":", 1)[-1].strip()
#                 break
#         if not reason:
#             reason = text
#         return decision, reason
#     except Exception as e:
#         return True, f"API error ({e}) — applying anyway"


# def apply_to_job(page, job: dict, index: int, profile: dict) -> str:
#     try:
#         job_url = job["url"]
#         title   = job.get("title", "Unknown")
#         company = job.get("company", "Unknown")

#         print(f"\n[{index}] {title} @ {company}")
#         print(f"     Location : {job.get('location', '')}")
#         print(f"     URL      : {job_url}")

#         # ── Navigate via search split-pane (NOT direct /jobs/view/ URL) ────────
#         #
#         # LinkedIn renders two completely different page layouts:
#         #   • /jobs/view/ID/  → standalone page; apply button often absent in headless
#         #   • /jobs/search/?currentJobId=ID  → split-pane; button always in DOM
#         #
#         # We use the split-pane URL so the Easy Apply button is reliably rendered.
#         job_id = job_url.rstrip("/").split("/")[-1]
#         pane_url = (
#             f"https://www.linkedin.com/jobs/search/"
#             f"?keywords={JOB_SEARCH_QUERY.replace(' ', '%20')}"
#             f"&location={JOB_LOCATION.replace(' ', '%20')}"
#             f"&currentJobId={job_id}"
#         )
#         if EASY_APPLY_ONLY:
#             pane_url += "&f_AL=true"

#         try:
#             page.goto(pane_url, wait_until="load", timeout=30000)
#         except Exception:
#             pass

#         # Wait for the job detail panel on the right side to render
#         _DETAIL_PANEL_WAIT = (
#             ".jobs-search__job-details, "
#             ".job-view-layout, "
#             ".jobs-details__main-content, "
#             ".jobs-description-content__text, "
#             "#job-details"
#         )
#         try:
#             page.wait_for_selector(_DETAIL_PANEL_WAIT, timeout=12000)
#         except Exception:
#             pass

#         # Scroll slightly to trigger lazy-loaded button rendering, then scroll back
#         page.evaluate("window.scrollTo(0, 200)")
#         time.sleep(1)
#         page.evaluate("window.scrollTo(0, 0)")
#         time.sleep(4)   # allow React to finish rendering the apply button

#         _screenshot(page)   # capture split-pane job detail

#         # Extract description and ask AI if this is a good fit
#         description = get_job_description(page)
#         fit, reason = is_good_fit(job, description)

#         if not fit:
#             _log(f"[{index}] {title} @ {company} — Skipped: {reason}", "warning")
#             _send_company(index, title, company, job.get("location", ""),
#                           "skipped", reason, description, job_url)
#             return "skipped"

#         _log(f"[{index}] {title} @ {company} — Good fit: {reason}", "found")

#         # Check if already applied
#         for sel in [
#             "text=Applied",
#             ".jobs-s-apply__application-link--applied",
#             "button[aria-label*='Applied']",
#         ]:
#             try:
#                 el = page.query_selector(sel)
#                 if el and el.is_visible():
#                     _log(f"[{index}] {title} @ {company} — Already applied", "info")
#                     _send_company(index, title, company, job.get("location", ""),
#                                   "already_applied", "Already applied", description, job_url)
#                     return "already_applied"
#             except Exception:
#                 continue

#         # ── Dismiss any Premium / promotional overlay ────────────────────────
#         for dismiss_sel in [
#             "button[aria-label*='Dismiss']",
#             "button[aria-label*='dismiss']",
#             ".artdeco-modal__dismiss",
#             "[data-test-modal-close-btn]",
#         ]:
#             try:
#                 el = page.query_selector(dismiss_sel)
#                 if el:
#                     el.click()
#                     time.sleep(0.4)
#             except Exception:
#                 pass

#         # ── Locate and click the Easy Apply button ───────────────────────────
#         #
#         # In LinkedIn's split-pane view there are TWO "Easy Apply" buttons:
#         #   • LEFT panel  — the job card in the search list (opens a mini-preview)
#         #   • RIGHT panel — the job detail card (opens the full application modal)
#         #
#         # We must target only the RIGHT panel button.  Right-panel containers:
#         #   .jobs-search__job-details  /  .job-view-layout  /  .jobs-details
#         #
#         # After clicking we confirm the modal with wait_for_selector (not just
#         # query_selector) to handle async rendering delays.

#         # Right-side detail panel containers (comma-separated for CSS selectors)
#         _DETAIL_PANEL = ".jobs-search__job-details, .job-view-layout, .jobs-details, .jobs-details__main-content"

#         # Modal selectors — broad enough to survive minor LinkedIn HTML changes
#         _MODAL_SELECTOR = (
#             ".jobs-easy-apply-content, "
#             ".jobs-easy-apply-modal, "
#             "[data-test-modal-id='easy-apply-modal'], "
#             "[data-test-modal='easy-apply-modal'], "
#             ".artdeco-modal[role='dialog']"
#         )

#         def _find_and_click_easy_apply(pg) -> bool:
#             """
#             Tries up to 5 times to click the Easy Apply button inside the
#             right-side detail panel and confirm the application modal appeared.
#             Returns True on success, False if all attempts fail.
#             """
#             for attempt in range(5):
#                 pg.evaluate("window.scrollTo(0, 0)")
#                 time.sleep(0.6)

#                 # ── Step 1: find the button scoped to the detail panel ────────
#                 btn_info = pg.evaluate("""
#                     () => {
#                         const PANEL_SEL = [
#                             '.jobs-search__job-details',
#                             '.job-view-layout',
#                             '.jobs-details',
#                             '.jobs-details__main-content',
#                             '.scaffold-layout__detail',
#                         ];
#                         const panel = PANEL_SEL.reduce(
#                             (found, s) => found || document.querySelector(s), null
#                         );
#                         const scope = panel || document;

#                         const EXCLUDED = ['save', 'dismiss', 'follow', 'share', 'report',
#                                           'message', 'connect', 'see more', 'show more'];
#                         const isApplyBtn = b => {
#                             if (!b.offsetParent) return false;  // not visible
#                             const aria = (b.getAttribute('aria-label') || '').toLowerCase();
#                             const text = (b.innerText || '').trim().toLowerCase();
#                             if (EXCLUDED.some(w => text === w || aria === w)) return false;
#                             if (text === '' && aria === '') return false;
#                             return (
#                                 aria.includes('easy apply') || text.includes('easy apply') ||
#                                 aria === 'apply'            || text === 'apply'            ||
#                                 aria.startsWith('apply to') || text.startsWith('apply to') ||
#                                 aria.includes('apply now')  || text.includes('apply now')  ||
#                                 aria.includes('apply on')   || text.includes('apply on')   ||
#                                 text.startsWith('apply')    || aria.startsWith('apply')
#                             );
#                         };

#                         // Also check anchor tags that look like apply buttons
#                         const allCandidates = [
#                             ...Array.from(scope.querySelectorAll('button')),
#                             ...Array.from(scope.querySelectorAll('a[href*="apply"]')),
#                         ];

#                         // Prefer Easy Apply first
#                         const easyBtn = allCandidates.find(b => {
#                             const aria = (b.getAttribute('aria-label') || '').toLowerCase();
#                             const text = (b.innerText || '').trim().toLowerCase();
#                             return aria.includes('easy apply') || text.includes('easy apply');
#                         });
#                         const btn = easyBtn || allCandidates.find(isApplyBtn);
#                         if (!btn) return null;

#                         btn.scrollIntoView({ behavior: 'instant', block: 'center' });

#                         const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
#                         const text = (btn.innerText || '').trim().toLowerCase();
#                         return {
#                             ariaLabel:   btn.getAttribute('aria-label') || '',
#                             text:        (btn.innerText || '').trim(),
#                             className:   btn.className || '',
#                             tagName:     btn.tagName,
#                             inPanel:     panel !== null,
#                             isEasyApply: aria.includes('easy apply') || text.includes('easy apply'),
#                         };
#                     }
#                 """)

#                 if not btn_info:
#                     _log(f"[{index}] Attempt {attempt + 1}: Apply button not found in DOM", "warning")
#                     # On odd attempts, try scrolling the page to trigger lazy rendering
#                     if attempt % 2 == 0:
#                         pg.evaluate("window.scrollTo(0, 400)")
#                         time.sleep(1)
#                         pg.evaluate("window.scrollTo(0, 0)")
#                     time.sleep(2.5)
#                     continue

#                 time.sleep(0.4)   # let scrollIntoView settle

#                 # ── Step 2: Playwright real click (force=True bypasses visibility) ──
#                 clicked = False

#                 # Build ordered selector list — prefer the scoped panel selector
#                 candidate_selectors = []
#                 if btn_info.get("ariaLabel"):
#                     aria_esc = btn_info["ariaLabel"].replace("'", "\\'")
#                     candidate_selectors.append(f"button[aria-label='{aria_esc}']")
#                 if btn_info.get("text"):
#                     candidate_selectors.append(f"button:has-text('{btn_info['text']}')")

#                 # Scoped selectors (right panel only) then global fallbacks
#                 _PANELS = [
#                     ".jobs-search__job-details",
#                     ".job-view-layout",
#                     ".jobs-details",
#                     ".jobs-details__main-content",
#                     ".scaffold-layout__detail",
#                 ]
#                 for panel in _PANELS:
#                     candidate_selectors += [
#                         f"{panel} button[aria-label*='Easy Apply']",
#                         f"{panel} button:has-text('Easy Apply')",
#                         f"{panel} .jobs-apply-button--top-card",
#                         f"{panel} button.jobs-apply-button",
#                         f"{panel} button[aria-label='Apply']",
#                         f"{panel} button[aria-label*='Apply now']",
#                         f"{panel} button[aria-label*='Apply to']",
#                         f"{panel} button:has-text('Apply')",
#                     ]

#                 # Global fallbacks (catches any matching button on page)
#                 candidate_selectors += [
#                     "button[aria-label*='Easy Apply']",
#                     "button:has-text('Easy Apply')",
#                     ".jobs-apply-button--top-card",
#                     "button.jobs-apply-button",
#                     ".jobs-s-apply button",
#                     "button[aria-label='Apply']",
#                     "button[aria-label*='Apply now']",
#                     "button[aria-label*='Apply to']",
#                     "button:has-text('Apply now')",
#                 ]

#                 for sel in candidate_selectors:
#                     try:
#                         loc = pg.locator(sel).first
#                         if loc.count() > 0:
#                             loc.scroll_into_view_if_needed()
#                             loc.click(force=True, timeout=4000)
#                             clicked = True
#                             break
#                     except Exception:
#                         continue

#                 if not clicked:
#                     _log(f"[{index}] Attempt {attempt + 1}: selector click failed", "warning")
#                     time.sleep(2)
#                     continue

#                 # ── Step 3: wait for modal (async render) ─────────────────────
#                 try:
#                     pg.wait_for_selector(_MODAL_SELECTOR, timeout=7000)
#                     return True
#                 except Exception:
#                     pass

#                 # Modal not confirmed — maybe a dialog without Easy Apply class?
#                 # Check for ANY new dialog that appeared after the click.
#                 any_dialog = pg.query_selector("[role='dialog']")
#                 if any_dialog:
#                     return True

#                 _log(f"[{index}] Attempt {attempt + 1}: click fired but modal did not appear", "warning")
#                 time.sleep(2)

#             return False

#         # ── Try to catch a new tab / popup opened by an "Apply" button ────────
#         # LinkedIn's non-Easy-Apply jobs open the company's ATS in a new tab.
#         # We register a popup handler BEFORE clicking the button so that if the
#         # button opens a new tab instead of a modal, we capture it.
#         _external_popup: list = []   # mutable container for the popup page

#         def _on_popup(popup_page) -> None:
#             _external_popup.append(popup_page)

#         page.context.on("page", _on_popup)

#         modal_opened = _find_and_click_easy_apply(page)

#         # Give Playwright up to 2 s to receive the popup event
#         deadline = time.time() + 2
#         while not _external_popup and time.time() < deadline:
#             time.sleep(0.2)

#         page.context.remove_listener("page", _on_popup)

#         # ── Path A: Easy Apply modal appeared ────────────────────────────────
#         if modal_opened:
#             _log(f"[{index}] Easy Apply modal opened — filling form...", "info")
#             _screenshot(page)

#             result = handle_easy_apply_modal(
#                 page, profile,
#                 job_title=title,
#                 job_description=description,
#             )
#             _screenshot(page)

#             status = "applied" if result == "applied" else "skipped"
#             r      = reason if result == "applied" else "Modal navigation failed"
#             _send_company(index, title, company, job.get("location", ""),
#                           status, r, description, job_url)
#             return result

#         # ── Path B: External ATS tab opened ──────────────────────────────────
#         if _external_popup:
#             ext_page = _external_popup[0]
#             try:
#                 ext_page.wait_for_load_state("domcontentloaded", timeout=20_000)
#             except Exception:
#                 pass

#             ext_url = ext_page.url
#             _log(f"[{index}] External ATS detected → {ext_url}", "info")
#             _screenshot(ext_page)

#             ext_result = _ext.apply_external(ext_page, ext_url, profile)

#             try:
#                 ext_page.close()
#             except Exception:
#                 pass

#             status = "applied" if ext_result == "applied" else "skipped"
#             r = reason if ext_result == "applied" else f"External ATS: {ext_result}"
#             _send_company(index, title, company, job.get("location", ""),
#                           status, r, description, ext_url)
#             return ext_result

#         # ── Path C: Neither modal nor popup ──────────────────────────────────
#         # If the Apply button is absent, LinkedIn most likely shows "Applied"
#         # because the user already submitted an application for this job.
#         # Check for that before marking as plain "skipped".
#         _ALREADY_APPLIED_SELECTORS = [
#             ".jobs-s-apply__application-link--applied",
#             "button[aria-label*='Applied']",
#             "[aria-label*='You applied']",
#             ".artdeco-inline-feedback__message",
#         ]
#         _ALREADY_APPLIED_TEXT = [
#             "you applied", "application was sent", "already applied",
#             "applied on", "application submitted",
#         ]
#         already = False
#         for sel in _ALREADY_APPLIED_SELECTORS:
#             try:
#                 el = page.query_selector(sel)
#                 if el and el.is_visible():
#                     already = True
#                     break
#             except Exception:
#                 pass
#         if not already:
#             try:
#                 body = (page.inner_text("body") or "").lower()
#                 already = any(t in body for t in _ALREADY_APPLIED_TEXT)
#             except Exception:
#                 pass

#         if already:
#             _log(f"[{index}] {title} @ {company} — Already applied (button hidden)", "info")
#             _send_company(index, title, company, job.get("location", ""),
#                           "already_applied", "Already applied", description, job_url)
#             return "already_applied"

#         _log(f"[{index}] {title} @ {company} — Apply button not clickable, skipping", "warning")
#         _send_company(index, title, company, job.get("location", ""),
#                       "skipped", "Apply button not clickable", description, job_url)
#         return "skipped"

#     except Exception as e:
#         print(f"     Error: {e}")
#         return "skipped"


# # ---------------------------------------------------------------------------
# # Screenshot
# # ---------------------------------------------------------------------------

# def take_screenshot(page, filename):
#     path = os.path.join(SCRIPT_DIR, filename)
#     page.screenshot(path=path)
#     print(f"Screenshot saved: {path}")


# # ---------------------------------------------------------------------------
# # Main
# # ---------------------------------------------------------------------------

# def main():
#     profile = load_profile()
#     print(f"Profile loaded: {profile['full_name']} | {profile['current_job_title']}")

#     # Init external-apply module with shared resources (standalone mode)
#     _ext._init(_openai_client, _track_usage, None)

#     with sync_playwright() as p:
#         os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
#         context = p.chromium.launch_persistent_context(
#             BROWSER_PROFILE_DIR,
#             headless=False,
#             args=[
#                 "--no-sandbox",
#                 "--disable-blink-features=AutomationControlled",
#                 "--start-maximized",
#             ],
#             viewport={"width": 1366, "height": 768},
#             user_agent=(
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                 "AppleWebKit/537.36 (KHTML, like Gecko) "
#                 "Chrome/120.0.0.0 Safari/537.36"
#             ),
#         )
#         page = context.new_page()

#         try:
#             login_linkedin(page)
#             take_screenshot(page, "linkedin_after_login.png")

#             job_cards = get_easy_apply_jobs(page, needed=MAX_APPLICATIONS)

#             results = {"applied": [], "skipped": [], "already_applied": []}

#             for i, job in enumerate(job_cards[:MAX_APPLICATIONS], start=1):
#                 status = apply_to_job(page, job, i, profile)
#                 results[status].append(i)
#                 time.sleep(2)

#             print("\n" + "=" * 50)
#             print("DONE!")
#             print(f"  Applied        : {len(results['applied'])}")
#             print(f"  Already applied: {len(results['already_applied'])}")
#             print(f"  Skipped        : {len(results['skipped'])}")
#             print("=" * 50)

#             log_path = os.path.join(SCRIPT_DIR, "linkedin_log.json")
#             with open(log_path, "w") as f:
#                 json.dump(results, f, indent=2)
#             print(f"Log saved to {log_path}")

#         except Exception as e:
#             print(f"Error: {e}")
#             take_screenshot(page, "linkedin_error.png")

#         finally:
#             input("\nPress Enter to close the browser...")
#             context.close()


# # ---------------------------------------------------------------------------
# # Programmatic entry point  (called by server.py)
# # ---------------------------------------------------------------------------

# def run_automation(profile: dict, logger=None) -> None:
#     """
#     Run the full LinkedIn automation pipeline.
#     Called by server.py's background thread.
#     `logger` is a SessionLogger instance that streams events over WebSocket.
#     """
#     global _logger
#     _logger = logger
#     _reset_usage()   # start fresh token counters for this run

#     # Inject shared resources into the external-apply module
#     _ext._init(_openai_client, _track_usage, logger)

#     applied_count = 0

#     with sync_playwright() as p:
#         # Profile folder is keyed by email — each account gets its own session.
#         # Switching credentials in the UI automatically uses a different folder,
#         # so the old session is never touched.
#         import hashlib
#         _email_slug = hashlib.md5((LINKEDIN_EMAIL or "").strip().lower().encode()).hexdigest()[:12]
#         _profile_dir = os.path.join(SCRIPT_DIR, f"linkedin_browser_profile_{_email_slug}")
#         os.makedirs(_profile_dir, exist_ok=True)

#         context = p.chromium.launch_persistent_context(
#             _profile_dir,
#             headless=True,
#             args=[
#                 "--no-sandbox",
#                 "--disable-blink-features=AutomationControlled",
#                 "--disable-dev-shm-usage",
#                 "--window-size=1366,768",
#             ],
#             viewport={"width": 1366, "height": 768},
#             user_agent=(
#                 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                 "AppleWebKit/537.36 (KHTML, like Gecko) "
#                 "Chrome/120.0.0.0 Safari/537.36"
#             ),
#         )
#         page = context.new_page()

#         # Start CDP screencast immediately after the page is created so that
#         # every subsequent navigation and interaction is streamed live.
#         # If CDP is unavailable the screencaster degrades silently; the manual
#         # _screenshot() calls inside apply_to_job() act as a safety net.
#         screencaster = CDPScreencaster(page, logger)
#         screencaster.start()

#         try:
#             _log("Opening LinkedIn browser...", "info")
#             login_status = login_linkedin(page)

#             if login_status == "wrong_credentials":
#                 # Error already logged inside login_linkedin — abort cleanly.
#                 _log("Automation stopped: fix your LinkedIn credentials and try again.", "error")
#                 if logger:
#                     logger.done()
#                 return

#             if login_status == "checkpoint":
#                 # Security check: in server mode we can't complete it — abort.
#                 _log(
#                     "Automation stopped: LinkedIn requires a security check "
#                     "(CAPTCHA or 2FA). Please log in manually once to clear it, "
#                     "then restart.",
#                     "error",
#                 )
#                 if logger:
#                     logger.done()
#                 return

#             if login_status == "failed":
#                 _log("Automation stopped: LinkedIn login page could not be loaded.", "error")
#                 if logger:
#                     logger.done()
#                 return

#             _log("Logged in — searching for jobs...", "info")

#             jobs = get_easy_apply_jobs(page, needed=MAX_APPLICATIONS)
#             _log(f"Found {len(jobs)} Easy Apply jobs (target: {MAX_APPLICATIONS})", "found")

#             for i, job in enumerate(jobs[:MAX_APPLICATIONS], start=1):
#                 # ── Page recovery ─────────────────────────────────────────────
#                 # LinkedIn's anti-bot detection or a popup/redirect during a
#                 # previous application can silently close the page object.
#                 # Detect this before each job and open a fresh page so the run
#                 # continues rather than crashing with "Target page... closed".
#                 if page.is_closed():
#                     _log("Browser page closed unexpectedly — opening a fresh page.", "warning")
#                     try:
#                         page = context.new_page()
#                         screencaster.stop()
#                         screencaster = CDPScreencaster(page, logger)
#                         screencaster.start()
#                         # Re-authenticate: persistent context keeps cookies but
#                         # a fresh page still needs to navigate to the feed.
#                         relogin_status = login_linkedin(page)
#                         if relogin_status == "wrong_credentials":
#                             _log("Re-login failed — wrong credentials. Stopping automation.", "error")
#                             break
#                     except Exception as recovery_exc:
#                         _log(f"Page recovery failed: {recovery_exc}", "error")
#                         break   # browser context is dead — abort the run

#                 status = apply_to_job(page, job, i, profile)

#                 if status == "applied":
#                     applied_count += 1
#                     if logger:
#                         logger.progress(applied_count, MAX_APPLICATIONS)
#                 # Random delay between jobs — reduces automation detection risk
#                 time.sleep(random.uniform(2.0, 4.5))

#             summary = f"Done! {applied_count}/{MAX_APPLICATIONS} applications submitted."
#             _log(summary, "success")

#             # Send cost summary to the frontend
#             cost = _cost_summary()
#             _log(
#                 f"GPT cost: ${cost['cost_usd']:.4f} "
#                 f"({cost['total_tokens']:,} tokens — "
#                 f"{cost['input_tokens']:,} in / {cost['output_tokens']:,} out)",
#                 "info",
#             )
#             if logger:
#                 logger.cost(cost)   # dedicated cost frame
#                 logger.done(summary)

#         except Exception as exc:
#             _log(f"Fatal error: {exc}", "error")
#             if logger:
#                 logger.fail(str(exc))

#         finally:
#             # Stop the CDP screencast before closing the browser so Chrome
#             # can process the Page.stopScreencast command cleanly.
#             screencaster.stop()
#             context.close()
#             _logger = None


# if __name__ == "__main__":
#     main()
"""
linkedin_apply.py
-----------------
Automatically applies to LinkedIn Easy Apply jobs using your profile.json.

Flow:
  Login → Search jobs (Easy Apply filter) → For each job:
    → Click Easy Apply → Fill contact info → Upload resume
    → Answer screening questions → Submit
"""

from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from openai import OpenAI
import base64
import datetime
import time
import json
import os
import re
import random

from . import external_apply as _ext

load_dotenv()

_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_ai_cache: dict = {}      # per-field GPT cache (legacy per-step path)
_answer_cache: dict = {}  # session-level screening answer cache (Tier 2)

# Set by server.py before calling run_automation(); None when running standalone.
_logger = None

# ── Token / cost tracking ─────────────────────────────────────────────────────
# gpt-4o-mini pricing (per 1M tokens, as of 2025)
_GPT_PRICE_INPUT  = 0.150 / 1_000_000   # $0.150 per 1M input tokens
_GPT_PRICE_OUTPUT = 0.600 / 1_000_000   # $0.600 per 1M output tokens

_total_input_tokens  = 0
_total_output_tokens = 0

def _track_usage(response) -> None:
    """Record token usage from any OpenAI API response."""
    global _total_input_tokens, _total_output_tokens
    if response.usage:
        _total_input_tokens  += response.usage.prompt_tokens
        _total_output_tokens += response.usage.completion_tokens

def _reset_usage() -> None:
    global _total_input_tokens, _total_output_tokens
    _total_input_tokens  = 0
    _total_output_tokens = 0

def _cost_summary() -> dict:
    """Return token counts and USD cost for this run."""
    cost = (
        _total_input_tokens  * _GPT_PRICE_INPUT +
        _total_output_tokens * _GPT_PRICE_OUTPUT
    )
    return {
        "input_tokens":  _total_input_tokens,
        "output_tokens": _total_output_tokens,
        "total_tokens":  _total_input_tokens + _total_output_tokens,
        "cost_usd":      round(cost, 6),
    }

def _log(message: str, log_type: str = "info") -> None:
    """Send a log line to the WebSocket session (if connected) and stdout."""
    if _logger is not None:
        getattr(_logger, log_type, _logger.info)(message)
    print(message)


def _human_delay(min_ms: int = 200, max_ms: int = 700) -> None:
    """Random pause to mimic human timing — reduces automation fingerprint."""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _screenshot(page) -> None:
    """
    Fallback: capture a single frame and stream it to the frontend.
    Used when CDPScreencaster is unavailable or as a supplementary snapshot.
    """
    if _logger is None or not hasattr(_logger, "screenshot"):
        return
    try:
        img_bytes = page.screenshot(type="jpeg", quality=55, full_page=False)
        _logger.screenshot(base64.b64encode(img_bytes).decode())
    except Exception:
        pass


class CDPScreencaster:
    """
    Streams live browser frames to the frontend via the Chrome DevTools Protocol.

    Chrome's ``Page.startScreencast`` command causes the browser to push a
    compressed JPEG after every composited frame.  Each frame must be
    acknowledged with ``Page.screencastFrameAck``; failure to do so causes
    Chrome to pause the stream.

    Integration with Playwright's sync API
    ──────────────────────────────────────
    Playwright's sync API is built on top of an internal asyncio event loop.
    Every blocking sync call (``page.goto``, ``page.click``, ``page.fill``,
    ``page.wait_for_selector``, ``page.wait_for_timeout``, …) yields control
    back to that loop, which is when CDP events are dispatched and
    ``_on_frame`` is invoked.  Between blocking Playwright calls (pure Python
    computation, ``time.sleep``, OpenAI API calls), no CDP events arrive.
    This is acceptable because the browser is not visually changing during
    those periods.

    Lifecycle
    ─────────
    1. Construct with the active Playwright ``Page`` and a ``SessionLogger``.
    2. Call ``start()`` once; it is idempotent.
    3. Frames stream automatically during all subsequent blocking Playwright
       operations.
    4. Call ``stop()`` in a ``finally`` block to release CDP resources cleanly.

    Thread safety
    ─────────────
    All ``_on_frame`` invocations originate from Playwright's internal event
    loop thread.  ``start()`` and ``stop()`` are called from the same
    worker thread that owns the Playwright context.  No locking is required
    because there is no cross-thread access to ``_session`` or ``_active``.
    """

    _MAX_FPS:    int = 10    # maximum frames forwarded to the frontend per second
    _QUALITY:    int = 60    # JPEG quality sent to Chrome (0–100)
    _MAX_WIDTH:  int = 1280  # Chrome will downscale frames to this width
    _MAX_HEIGHT: int = 800

    def __init__(self, page, logger) -> None:
        self._page    = page
        self._logger  = logger
        self._session = None          # playwright CDPSession handle
        self._active  = False         # True only between start() and stop()
        self._last_ts = 0.0           # monotonic timestamp of the last forwarded frame

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Attach a CDP session to the page and begin the screencast.
        Safe to call multiple times; subsequent calls are no-ops.
        """
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
                # Ask Chrome to emit every composited frame; we throttle in
                # _on_frame rather than relying on Chrome's own frame-skip
                # parameter, which is not well-defined across versions.
                "everyNthFrame": 1,
            })
            self._active = True
            print("[CDPScreencaster] Screencast started.")
        except Exception as exc:
            # CDP may be unavailable in certain Playwright/browser configurations.
            # Degrade gracefully: manual _screenshot() calls remain functional.
            print(f"[CDPScreencaster] start() failed ({exc!r}); "
                  "falling back to manual screenshots.")

    def stop(self) -> None:
        """
        Stop the screencast and detach the CDP session.
        Safe to call when not active; idempotent.
        """
        if not self._active:
            return
        self._active = False

        # Best-effort: ignore errors caused by the browser already being closed.
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

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_frame(self, params: dict) -> None:
        """
        Invoked by Playwright for each ``Page.screencastFrame`` CDP event.

        Chrome DevTools Protocol frame payload:
          data      – base64-encoded JPEG string (the actual pixel data)
          metadata  – dict: timestamp, deviceWidth, deviceHeight, scrollOffsetX/Y, …
          sessionId – integer token; *must* be echoed back via screencastFrameAck
                      or Chrome will pause the stream indefinitely
        """
        session_id: int = params.get("sessionId", 0)

        # Acknowledge immediately so Chrome never stalls waiting for our ack,
        # regardless of whether we forward this particular frame.
        self._ack(session_id)

        if not self._active or self._logger is None:
            return

        # Throttle: silently drop frames that arrive faster than _MAX_FPS.
        now = time.monotonic()
        if now - self._last_ts < 1.0 / self._MAX_FPS:
            return
        self._last_ts = now

        try:
            self._logger.screenshot(params["data"])
        except Exception:
            # Never let a delivery failure propagate into the automation loop.
            pass

    def _ack(self, session_id: int) -> None:
        """Acknowledge a screencast frame to keep Chrome's stream flowing."""
        try:
            if self._session:
                self._session.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            pass


def _send_company(index: int, title: str, company: str, location: str,
                  status: str, reason: str = "",
                  description: str = "", url: str = "") -> None:
    """Send structured company result to the frontend companies table."""
    if _logger is not None and hasattr(_logger, "company"):
        _logger.company({
            "index":       index,
            "title":       title,
            "company":     company,
            "location":    location,
            "status":      status,
            "reason":      reason,
            "description": description,
            "url":         url,
        })


def load_resume_text() -> str:
    path = os.path.join(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "resume_text.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


RESUME_TEXT = load_resume_text()


def ask_user_fallback(question: str, options: list = None) -> str:
    """
    Ask the user directly in the terminal when AI cannot determine the answer.
    Called in real-time while the browser is open.
    """
    print(f"\n  {'='*55}")
    print(f"  [USER INPUT NEEDED — browser is paused]")
    print(f"  Question: {question}")
    if options:
        print(f"  Available options:")
        for i, opt in enumerate(options, 1):
            print(f"    {i}. {opt}")
        while True:
            try:
                raw = input(f"  Enter number (1-{len(options)}) or type the exact answer: ").strip()
                if raw.isdigit() and 1 <= int(raw) <= len(options):
                    chosen = options[int(raw) - 1]
                    print(f"  You chose: {chosen}")
                    print(f"  {'='*55}\n")
                    return chosen
                elif raw:
                    print(f"  You typed: {raw}")
                    print(f"  {'='*55}\n")
                    return raw
            except (EOFError, KeyboardInterrupt):
                return options[0] if options else ""
    else:
        try:
            ans = input(f"  Type your answer: ").strip()
            print(f"  {'='*55}\n")
            return ans
        except (EOFError, KeyboardInterrupt):
            return ""


def get_ai_answer(question: str, field_type: str, profile: dict,
                  options: list = None, ask_user_if_unsure: bool = True) -> str:
    """
    Ask GPT-4o-mini to answer a screening question using resume + profile context.
    field_type: 'text', 'number', 'yes_no', 'dropdown'
    options:    for dropdowns, the list of exact option strings to choose from
    ask_user_if_unsure: if True and AI answer doesn't match any option, ask user via terminal
    """
    cache_key = f"{question}|{field_type}|{','.join(options or [])}"
    if cache_key in _ai_cache:
        return _ai_cache[cache_key]

    options_block = ""
    if options:
        options_block = (
            "\nAvailable options — you MUST return EXACTLY one of these strings, copied verbatim:\n"
            + "\n".join(f"  - {o}" for o in options)
        )

    prompt = f"""You are filling a LinkedIn Easy Apply screening form on behalf of this candidate.
Your goal: pick the answer that makes the candidate appear most qualified while staying truthful to their resume.

--- CANDIDATE PROFILE ---
Name: {profile['full_name']}
Total experience: {profile.get('years_of_experience', '1')} years
Current role: {profile['current_job_title']} at {profile['current_company']}
City: {profile['current_city']}
Notice period: {profile.get('notice_period', '30')} days
Current salary (INR/year): {profile.get('current_salary', '')}
Expected salary (INR/year): {profile.get('expected_salary', 700000)}
LinkedIn: {profile.get('linkedin_url', '')}
GitHub: {profile.get('github_url', '')}
Phone: {profile['phone']}

--- FULL RESUME ---
{RESUME_TEXT}

--- QUESTION ---
{question}
Field type: {field_type}
{options_block}

--- RULES ---
- yes_no        → return exactly "Yes" or "No"
- number        → return only a digit. NEVER return 0 for experience; minimum is 1.
                  Check resume for the actual experience with the specific skill/tech mentioned.
- text          → if options are given, short phrase; if no options (textarea / cover letter),
                  write 2–4 professional sentences using the resume and profile above.
                  Be specific, confident, and concise. Do NOT add a salutation or closing.
- dropdown      → return EXACTLY one of the provided option strings, copied verbatim (case-sensitive).
                  If experience options are present (e.g. "0-1 years", "1-2 years", "2+ years"),
                  infer from resume internships; default to the lowest positive range (e.g. "0-1 years"
                  or "1-2 years") for any tech found in resume.
- Work authorization / eligibility in India → "Yes"
- Notice period  → "30"
- Salary         → "700000"
- Current city   → "Delhi"
- If a technology is NOT in the resume, pick the smallest/least-experience option available.
- Return ONLY the answer — no explanation, no surrounding quotes or punctuation.
"""

    # Textarea / cover-letter fields need room for a paragraph;
    # all other field types fit comfortably in 60 tokens.
    max_tok = 300 if field_type == "text" and not options else 60

    try:
        response = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tok,
        )
        _track_usage(response)
        answer = response.choices[0].message.content.strip().strip('"').strip("'")
        print(f"     AI answered '{question[:60]}' → '{answer}'")

        # For dropdowns: validate AI returned a real option
        if options and field_type == "dropdown":
            # Exact match
            if answer in options:
                _ai_cache[cache_key] = answer
                return answer
            # Case-insensitive match
            lower_map = {o.lower(): o for o in options}
            if answer.lower() in lower_map:
                matched = lower_map[answer.lower()]
                _ai_cache[cache_key] = matched
                return matched
            # Partial match (AI answer substring of option or vice-versa)
            for opt in options:
                if answer.lower() in opt.lower() or opt.lower() in answer.lower():
                    _ai_cache[cache_key] = opt
                    print(f"     Partial match → '{opt}'")
                    return opt
            # Fuzzy word-overlap: score each option by how many words from
            # the AI answer appear in the option text — pick highest scorer.
            answer_words = set(re.split(r'\W+', answer.lower())) - {"", "the", "a", "an", "of", "with", "and", "or"}
            best_opt, best_score = None, -1
            for opt in options:
                opt_words = set(re.split(r'\W+', opt.lower()))
                score = len(answer_words & opt_words)
                if score > best_score:
                    best_opt, best_score = opt, score
            if best_opt and best_score > 0:
                _ai_cache[cache_key] = best_opt
                print(f"     Fuzzy match → '{best_opt}' (score {best_score})")
                return best_opt
            # Change C: in server/headless mode skip ask_user_fallback;
            # auto-pick the safest option without blocking stdin.
            if ask_user_if_unsure:
                if _logger is not None:
                    # Server mode: auto-pick affirmative option, or first option
                    _YES_WORDS = {"yes", "y", "true", "1", "agree", "accept"}
                    affirmative = next(
                        (o for o in options if o.strip().lower() in _YES_WORDS), None
                    )
                    chosen = affirmative or options[0]
                    print(f"     Server-mode auto-pick → '{chosen}' (AI returned '{answer}')")
                    _ai_cache[cache_key] = chosen
                    return chosen
                else:
                    # Standalone terminal mode: ask user
                    print(f"     AI answer '{answer}' didn't match any option — asking user.")
                    user_ans = ask_user_fallback(question, options)
                    _ai_cache[cache_key] = user_ans
                    return user_ans
            # Last resort: first option (placeholders already stripped by caller)
            return options[0] if options else answer

        _ai_cache[cache_key] = answer
        return answer

    except Exception as e:
        print(f"     AI answer error: {e}")
        if options and ask_user_if_unsure:
            if _logger is not None:
                # Server mode: never block — pick first available real option
                return options[0] if options else ""
            return ask_user_fallback(question, options)
        return ""

SCRIPT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# Persistent browser profile — saves cookies/session so LinkedIn doesn't
# trigger a security check on every run.
BROWSER_PROFILE_DIR = os.path.join(SCRIPT_DIR, "linkedin_browser_profile")

# =============================================
# CONFIG
# =============================================
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
JOB_SEARCH_QUERY  = "Data Scientist"
JOB_LOCATION      = "India"
MAX_APPLICATIONS  = 20
EASY_APPLY_ONLY   = True   # True = LinkedIn Easy Apply filter; False = all jobs (external apply)
# =============================================


def load_profile() -> dict:
    path = os.path.join(SCRIPT_DIR, "profile.json")
    if not os.path.exists(path):
        raise FileNotFoundError("profile.json not found. Run parse_resume.py first.")
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _js_fill_login(page) -> bool:
    """
    Fill the LinkedIn login form reliably for both classic and React-based forms.

    Root causes addressed:
      - LinkedIn renders 2 matching inputs; the first is a hidden React
        hydration duplicate.  page.fill() / page.click() enforce visibility
        and time out on it.  We skip hidden elements explicitly.
      - plain Event('input') does NOT update React's controlled-component
        state — React reads InputEvent.data / InputEvent.inputType.  Using a
        proper InputEvent ensures React's onChange fires and internal state
        is populated before form submission.

    Strategy waterfall (per field):
      1. page.fill(force=True)  — bypasses visibility; Playwright dispatches
                                   trusted events React honours.
      2. JS focus + keyboard.type() — real keystrokes via CDP; works when
                                       fill() is intercepted by React guards.
      3. nativeInputValueSetter + InputEvent — sets DOM value directly and
                                               fires a proper InputEvent so
                                               React state updates.
    """
    _EMAIL_SELS = [
        "input#username",
        "input#session_key",
        "input[autocomplete='username']",
        "input[autocomplete='email']",
        "input[type='email']",
        "input[type='text']",
    ]
    _PASS_SELS = [
        "input#session_password",
        "input#password",
        "input[autocomplete='current-password']",
        "input[type='password']",
    ]

    def _fill_field(selectors: list, value: str) -> bool:
        for sel in selectors:
            try:
                # Find the index of the first non-hidden element
                idx = page.evaluate("""({sel}) => {
                    const els = Array.from(document.querySelectorAll(sel));
                    if (!els.length) return -1;
                    // prefer a visible (non-zero-size) element
                    const vi = els.findIndex(e =>
                        e.offsetParent !== null ||
                        (e.getBoundingClientRect().width > 0 &&
                         e.getBoundingClientRect().height > 0)
                    );
                    return vi >= 0 ? vi : 0;   // fall back to first if all hidden
                }""", {"sel": sel})

                if idx == -1:
                    continue   # selector not in DOM at all

                # ── Strategy 1: page.fill with force ─────────────────────────
                # force=True skips Playwright's visibility / actionability check
                try:
                    loc = page.locator(sel).nth(idx)
                    loc.fill(value, force=True, timeout=3000)
                    actual = page.evaluate(
                        "({sel, idx}) => (document.querySelectorAll(sel)[idx]||{}).value??''",
                        {"sel": sel, "idx": idx},
                    )
                    print(f"  [fill]  '{sel}'[{idx}] → actual='{actual[:30]}'")
                    if actual:
                        return True
                except Exception as e1:
                    print(f"  [fill]  '{sel}'[{idx}] failed: {e1}")

                # ── Strategy 2: JS focus + Playwright keyboard.type ───────────
                try:
                    page.evaluate(
                        "({sel, idx}) => { const e = document.querySelectorAll(sel)[idx]; if(e){e.focus();} }",
                        {"sel": sel, "idx": idx},
                    )
                    page.keyboard.press("Control+a")
                    page.keyboard.press("Delete")
                    page.keyboard.type(value, delay=40)
                    time.sleep(0.15)
                    actual = page.evaluate(
                        "({sel, idx}) => (document.querySelectorAll(sel)[idx]||{}).value??''",
                        {"sel": sel, "idx": idx},
                    )
                    print(f"  [type]  '{sel}'[{idx}] → actual='{actual[:30]}'")
                    if actual:
                        return True
                except Exception as e2:
                    print(f"  [type]  '{sel}'[{idx}] failed: {e2}")

                # ── Strategy 3: nativeInputValueSetter + InputEvent ───────────
                # Uses InputEvent (not plain Event) so React's controlled
                # component state is updated via its synthetic onChange handler.
                try:
                    ok = page.evaluate("""({sel, idx, val}) => {
                        const el = document.querySelectorAll(sel)[idx];
                        if (!el) return false;
                        // Set the DOM value bypassing React's getter
                        const setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, val);
                        el.focus();
                        // InputEvent with inputType+data updates React state
                        el.dispatchEvent(new InputEvent('input', {
                            bubbles: true, cancelable: false,
                            inputType: 'insertText', data: val
                        }));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return !!el.value;
                    }""", {"sel": sel, "idx": idx, "val": value})
                    time.sleep(0.15)
                    actual = page.evaluate(
                        "({sel, idx}) => (document.querySelectorAll(sel)[idx]||{}).value??''",
                        {"sel": sel, "idx": idx},
                    )
                    print(f"  [react] '{sel}'[{idx}] → ok={ok} actual='{actual[:30]}'")
                    if actual:
                        return True
                except Exception as e3:
                    print(f"  [react] '{sel}'[{idx}] failed: {e3}")

            except Exception as _e:
                print(f"  '{sel}' outer error: {_e}")
                continue
        return False

    email_ok = _fill_field(_EMAIL_SELS, LINKEDIN_EMAIL or "")
    pass_ok  = _fill_field(_PASS_SELS,  LINKEDIN_PASSWORD or "")
    return email_ok and pass_ok


def login_linkedin(page) -> str:
    """
    Log in to LinkedIn with the credentials from environment variables.

    Returns one of:
      "success"            — logged in successfully
      "wrong_credentials"  — LinkedIn rejected email/password
      "checkpoint"         — security check / CAPTCHA required
      "failed"             — login form not found or unknown error
    """
    print("Opening LinkedIn...")

    # 'load' fires once HTML + resources are done — LinkedIn never reaches
    # 'networkidle' because it streams background requests indefinitely.
    try:
        page.goto("https://www.linkedin.com/login",
                  wait_until="load", timeout=30000)
    except Exception:
        pass  # page may still be usable after a timeout

    # ── Already logged in? (persistent browser context keeps cookies) ─────────
    # When the session cookie is still valid, LinkedIn redirects /login straight
    # to the feed.  Detect that before waiting for a form that will never appear.
    url_after_goto = page.url
    if any(x in url_after_goto for x in ("feed", "/in/", "mynetwork", "jobs", "home")):
        print("Already logged in (session cookie valid).")
        _log("LinkedIn session restored from saved profile — skipping login.", "info")
        return "success"

    # Also check for checkpoint immediately after goto
    if any(x in url_after_goto for x in ("checkpoint", "challenge", "captcha", "two-step", "pin")):
        _log("LinkedIn security check detected on session restore.", "warning")
        return "checkpoint"

    # Wait until the login form inputs actually appear (up to 20 s)
    print("Waiting for login form...")
    try:
        page.wait_for_function(
            """() => !!(
                document.querySelector('input#session_key') ||
                document.querySelector('input#username') ||
                document.querySelector('input[type="email"]') ||
                document.querySelector('input[type="text"]')
            )""",
            timeout=20000,
        )
    except Exception:
        # Last chance: maybe we landed on the feed during the wait
        url_now = page.url
        if any(x in url_now for x in ("feed", "/in/", "mynetwork", "jobs", "home")):
            print("Already logged in (redirected during wait).")
            _log("LinkedIn session active — skipping login.", "info")
            return "success"
        print("Login form not detected.")
        page.screenshot(path=os.path.join(SCRIPT_DIR, "linkedin_login_debug.png"))
        if _logger is None:
            input("Please log in manually in the browser window, then press Enter here...")
        return "failed"

    time.sleep(1)

    print("Entering credentials...")
    filled = _js_fill_login(page)

    if not filled:
        print("Could not inject credentials.")
        if _logger is None:
            input("Log in manually then press Enter here...")
        return "failed"

    time.sleep(0.5)

    # Submit the form
    submitted = False
    for sel in [
        "button[type='submit']",
        "button[data-litms-control-urn*='login']",
        "button.sign-in-form__submit-button",
        "button:has-text('Sign in')",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                submitted = True
                break
        except Exception:
            continue

    if not submitted:
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass

    # Wait for LinkedIn to respond — either redirect to feed or show an error
    time.sleep(4)

    url = page.url

    # ── Success: redirected to the main feed or profile ──────────────────────
    if any(x in url for x in ("feed", "/in/", "mynetwork", "jobs")):
        print("Login successful!")
        _log("LinkedIn login successful.", "info")
        return "success"

    # ── Security checkpoint (CAPTCHA / unusual activity / 2FA) ───────────────
    if any(x in url for x in ("checkpoint", "challenge", "captcha", "two-step", "pin")):
        print("Security check required.")
        _log("LinkedIn security check detected — please complete it in the browser.", "warning")
        if _logger is None:
            input("Complete the security check then press Enter...")
        return "checkpoint"

    # ── Wrong credentials: detect LinkedIn's inline error messages ───────────
    #
    # LinkedIn shows errors in two ways:
    #   1. Inline error spans with IDs  #error-for-password  /  #error-for-username
    #   2. A red alert banner with class .alert or role="alert"
    #
    _WRONG_CRED_SELECTORS = [
        "#error-for-password",
        "#error-for-username",
        "span#error-for-password",
        "span#error-for-username",
        ".form__label--error",
        "[data-test-id='error-for-password']",
    ]
    _WRONG_CRED_PHRASES = [
        "that's not the right password",
        "incorrect password",
        "wrong password",
        "email address isn't associated",
        "couldn't find a linkedin account",
        "hmm, that's not the right password",
        "please enter a valid email",
        "incorrect email or password",
    ]

    for err_sel in _WRONG_CRED_SELECTORS:
        try:
            el = page.query_selector(err_sel)
            if el and el.is_visible():
                err_text = (el.inner_text() or "").strip()
                print(f"Wrong credentials detected: {err_text}")
                _log(
                    f"❌ LinkedIn login failed — wrong email or password. "
                    f"Please check your credentials and try again. ({err_text})",
                    "error",
                )
                return "wrong_credentials"
        except Exception:
            pass

    try:
        body_text = (page.inner_text("body") or "").lower()
        for phrase in _WRONG_CRED_PHRASES:
            if phrase in body_text:
                print(f"Wrong credentials phrase found: '{phrase}'")
                _log(
                    "❌ LinkedIn login failed — wrong email or password. "
                    "Please check your credentials and try again.",
                    "error",
                )
                return "wrong_credentials"
    except Exception:
        pass

    # ── Fallback: still on login page = rejected, unknown reason ─────────────
    if "login" in url or "authwall" in url or "uas/login" in url:
        _log(
            "❌ LinkedIn login failed — credentials were not accepted. "
            "Please verify your email and password.",
            "error",
        )
        return "wrong_credentials"

    # ── Unknown state ─────────────────────────────────────────────────────────
    print(f"Login state unclear (URL: {url})")
    _log(f"LinkedIn login state unclear (URL: {url}) — proceeding anyway.", "warning")
    if _logger is None:
        input("Press Enter to continue...")
    return "success"   # optimistic: assume logged in on unknown URLs


# ---------------------------------------------------------------------------
# Job search
# ---------------------------------------------------------------------------

_EXTRACT_CARDS_JS = """
() => {
    const seen = new Set();
    const results = [];
    const cards = document.querySelectorAll(
        '.job-card-container, .jobs-search-results__list-item'
    );
    for (const card of cards) {
        const anchor = card.querySelector('a[href*="/jobs/view/"]');
        if (!anchor) continue;
        const url = anchor.href.split('?')[0];
        if (seen.has(url)) continue;
        seen.add(url);
        const titleEl   = card.querySelector(
            '.job-card-list__title--link, .job-card-list__title, '
            + '.job-card-container__link span[aria-hidden="true"]'
        );
        const companyEl = card.querySelector(
            '.job-card-container__primary-description, '
            + '.artdeco-entity-lockup__subtitle span, '
            + '.job-card-container__company-name'
        );
        const locationEl = card.querySelector(
            '.job-card-container__metadata-item, '
            + '.artdeco-entity-lockup__caption li'
        );
        results.push({
            url:      url,
            title:    titleEl    ? titleEl.innerText.trim()    : anchor.innerText.trim(),
            company:  companyEl  ? companyEl.innerText.trim()  : '',
            location: locationEl ? locationEl.innerText.trim() : '',
        });
    }
    return results;
}
"""

def get_easy_apply_jobs(page, needed: int = 10) -> list[dict]:
    """
    Collect Easy Apply job cards by paginating LinkedIn's search results via
    the ``&start=N`` URL parameter.

    Why scrolling never worked reliably
    ─────────────────────────────────────
    LinkedIn's job list uses virtual DOM rendering in headless Chrome: only
    the cards visible inside the viewport are kept in the DOM.  Changing a
    panel's ``scrollTop`` in JavaScript does NOT fire the IntersectionObserver
    callbacks that LinkedIn attaches to lazy-load new cards — so the DOM card
    count never grew past whatever was rendered on the initial page load (7 in
    this case).

    Why URL pagination is the correct fix
    ──────────────────────────────────────
    LinkedIn exposes stable server-side pagination via ``&start=N`` (0, 25,
    50 …).  Each page is a fresh server request that returns the next batch of
    25 results fully rendered.  No scrolling, no IntersectionObserver, no
    selector guessing — just load the next URL and extract cards.
    """
    _log(f"Searching for '{JOB_SEARCH_QUERY}' jobs in {JOB_LOCATION}...", "info")

    base_url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={JOB_SEARCH_QUERY.replace(' ', '%20')}"
        f"&location={JOB_LOCATION.replace(' ', '%20')}"
        f"&sortBy=R"           # sort by relevance
    )
    if EASY_APPLY_ONLY:
        base_url += "&f_AL=true"   # LinkedIn's Easy Apply filter

    seen_urls: set[str] = set()
    all_jobs:  list[dict] = []

    # LinkedIn shows up to 25 jobs per page.  Load just enough pages to
    # satisfy ``needed``, plus one extra page as a buffer for deduplication.
    pages_required = (needed // 25) + 2

    for page_idx in range(pages_required):
        if len(all_jobs) >= needed:
            break

        start  = page_idx * 25
        url    = f"{base_url}&start={start}"

        try:
            page.goto(url, wait_until="load", timeout=30000)
        except Exception:
            pass

        # Wait for at least one card to appear; bail out if the page is empty
        try:
            page.wait_for_selector(
                ".job-card-container, .jobs-search-results__list-item",
                timeout=10000,
            )
        except Exception:
            _log(f"No job cards found on page {page_idx + 1} — stopping.", "warning")
            break

        time.sleep(1.5)   # let deferred JS finish rendering

        batch = page.evaluate(_EXTRACT_CARDS_JS)
        new_on_page = 0
        for job in batch:
            if job["url"] not in seen_urls:
                seen_urls.add(job["url"])
                all_jobs.append(job)
                new_on_page += 1

        _log(f"Page {page_idx + 1}: found {new_on_page} new jobs "
             f"(total so far: {len(all_jobs)})", "info")

        if new_on_page == 0:
            # LinkedIn returned a page with no new cards — end of results
            break

    # Trim to exactly what the user requested
    jobs = all_jobs[:needed]
    _log(f"Collected {len(jobs)} Easy Apply jobs (requested {needed})", "found")
    for j in jobs:
        print(f"   • {j['title']} @ {j['company']}  [{j['location']}]")
    return jobs


# ---------------------------------------------------------------------------
# Easy Apply modal — vision-driven handler
# ---------------------------------------------------------------------------

_MODAL_VISION_SYSTEM = """You are an AI agent filling a LinkedIn Easy Apply form on behalf of a job candidate.
You receive a list of interactive elements extracted from the modal DOM and the candidate's profile.
Return the SINGLE best next action as JSON (no markdown, no code block):

{
  "action": "fill" | "typeahead" | "click" | "select" | "upload_resume" | "next" | "done",
  "selector": "CSS selector for target element (empty for upload_resume / next / done)",
  "value": "text to type OR exact option text from options[] (empty for click / next / done)",
  "reason": "one sentence"
}

━━━ ACTION RULES ━━━
  fill          — type into plain text / email / tel / number / textarea fields
  typeahead     — type into autocomplete/combobox fields (isTypeahead=true) — value is what to search for
                  The system will type the value and select the first matching suggestion automatically.
  click         — radio button LABELS, checkboxes, custom dropdown triggers, toggle buttons
  select        — NATIVE <select> elements — value MUST be the EXACT option text from options[]
  upload_resume — attach resume PDF (no selector needed)
  next          — every required field on this page is correctly filled → click Next/Review/Submit
  done          — a success / "Application submitted" confirmation is visible

━━━ FIELD-BY-FIELD GUIDANCE ━━━

Text / email / phone:
  - First name / last name: split full_name at the first space.
  - Phone: use phone_digits (digits only, NO country code like +91 or +1).
  - City / location: check isTypeahead — if true, use "typeahead" action with current_city value.
  - Email: use the email from the candidate profile.

Numeric "years of experience" fields:
  - ALWAYS return a WHOLE INTEGER (e.g. 1, 2, 3). NEVER use decimals like 1.5 or 0.5.
  - If the label asks about a SPECIFIC skill (e.g. "years with Python"):
      • Use floor(years_of_experience) if the skill is in the candidate's skills list.
      • Use 1 if the candidate has the skill but total experience is < 1 year.
      • Use 0 only if the candidate genuinely does not have the skill.
  - If the label asks for TOTAL years of experience: use floor(years_of_experience).

Typeahead / autocomplete fields (isTypeahead = true):
  - Use "typeahead" action. The system will type and select the first suggestion.
  - City/location fields: type the city name (e.g. "Delhi", "Bangalore").
  - Country fields: type "India".
  - Company fields: type the company name from the profile.
  - Skills fields: type the most relevant skill.

Radio buttons / Yes-No questions:
  - Sponsorship required / visa sponsorship: click "No".
  - Authorized to work / work eligibility: click "Yes".
  - Currently employed / working: click "Yes".
  - Willing to relocate: click "Yes".
  - Comfortable commuting / willing to work on-site: click "Yes".
  - Any other Yes/No: use the most positive/qualified answer for a strong candidate.
  - ALWAYS use selector for input[type="radio"] — the code will automatically find
    and click the correct LABEL. Do NOT try to target label elements directly.

Native <select> dropdowns:
  - Use "select" action. Value MUST exactly match one entry from the options[] list.
  - For notice period: pick the option closest to notice_period days.
  - For currency / country: pick "India" / "INR" where relevant.
  - For education level: pick the highest degree the candidate holds.
  - For gender / demographic fields (optional): pick "Prefer not to say" or "Decline to self-identify".

Custom dropdowns (non-native, not typeahead):
  - Use "click" to open the trigger, then on the NEXT step "click" the matching option.

Checkboxes:
  - Use "click" on the label or the checkbox element.
  - "Follow company" checkbox: skip it (it is optional — do not click it).

Cover letter / additional info text areas:
  - Write 2–3 concise sentences tailored to the role using the candidate's title and skills.

Salary / CTC fields:
  - current_salary → current_ctc value from profile.
  - expected_salary → expected_ctc value from profile.
  - If only annual CTC is asked, use the value as-is (do not divide).

LinkedIn URL / GitHub URL / Portfolio:
  - Fill with the exact URL from the profile (linkedin_url, github_url, portfolio_url).
  - If a field is optional and the profile value is empty, skip it.

Date fields (month/year):
  - For "Date" type inputs, use fill with format "MM/YYYY" or "YYYY-MM" as shown by placeholder.
  - If it's a select for month: select the month name or number. For year: select the 4-digit year.

━━━ CRITICAL RULES ━━━
1. Check the "currentValue" field of each element — if it is already correctly filled, SKIP that element.
2. Fill EVERY visible empty required field on this page before returning "next".
3. NEVER repeat an action from "Already tried" — choose a different selector or method.
4. If the last action failed, try a completely different approach (different selector, different action type).
5. Return "next" ONLY when ALL required fields are filled.
6. Return "done" ONLY when a success/confirmation message is visible on screen.
7. Do NOT interact with "Follow company" checkboxes — skip them.
8. For demographic/optional fields (gender, race, disability): always pick "Prefer not to say".
"""

_SUCCESS_TEXTS = [
    "your application was sent",
    "application submitted",
    "applied successfully",
    "successfully applied",
    "you've applied",
]

_NAV_SELECTORS = [
    "button[aria-label='Submit application']",
    "button:has-text('Submit application')",
    "button[aria-label='Continue to next step']",
    "button[aria-label='Review your application']",
    "button:has-text('Review')",
    "button:has-text('Next')",
    "button:has-text('Continue')",
    "button:has-text('Save')",
    "button[aria-label='Save']",
]


def _modal_is_success(page) -> bool:
    """Return True if LinkedIn shows an application-submitted confirmation."""
    try:
        body = (page.inner_text("body") or "").lower()
        return any(t in body for t in _SUCCESS_TEXTS)
    except Exception:
        return False


def _handle_resume_selection(page, profile: dict) -> bool:
    """
    Detect the LinkedIn resume-selection step (2+ resume cards visible) and
    deterministically pick the uploaded CV — no GPT needed for this step.

    LinkedIn shows:
      • One card per uploaded resume  (label contains the filename)
      • One card for "LinkedIn Profile" (auto-generated)

    Strategy:
      1. Try to match the card whose label text contains our uploaded filename.
      2. Fall back to the first card that is NOT "LinkedIn Profile".
      3. Last resort: pick whatever the first card is.

    Returns True if this was a resume-selection page (handled + Next clicked).
    Returns False if there were fewer than 2 cards (not a selection page).
    """
    try:
        cards = page.query_selector_all("input[id^='jobsDocumentCardToggle']")
        if len(cards) < 2:
            return False

        resume_path = profile.get("resume_path", "")
        resume_name = os.path.basename(resume_path).lower() if resume_path else ""

        chosen_label = None

        # Pass 1 — match by uploaded filename
        if resume_name:
            for card in cards:
                cid   = card.get_attribute("id") or ""
                lid   = cid.replace("Toggle", "ToggleLabel")
                label = page.query_selector(f"#{lid}") or page.query_selector(f"label[for='{cid}']")
                if label:
                    txt = (label.inner_text() or "").lower()
                    # Match on first ~12 chars of filename (avoids extension issues)
                    if resume_name[:12] in txt:
                        chosen_label = label
                        break

        # Pass 2 — any non-LinkedIn-profile card
        if not chosen_label:
            for card in cards:
                cid   = card.get_attribute("id") or ""
                lid   = cid.replace("Toggle", "ToggleLabel")
                label = page.query_selector(f"#{lid}") or page.query_selector(f"label[for='{cid}']")
                if label:
                    txt = (label.inner_text() or "").lower()
                    if "linkedin" not in txt and "profile" not in txt:
                        chosen_label = label
                        break

        # Pass 3 — just take the first card
        if not chosen_label and cards:
            cid   = cards[0].get_attribute("id") or ""
            lid   = cid.replace("Toggle", "ToggleLabel")
            chosen_label = (
                page.query_selector(f"#{lid}") or
                page.query_selector(f"label[for='{cid}']")
            )

        if chosen_label:
            try:
                chosen_label.scroll_into_view_if_needed()
                chosen_label.click()
                time.sleep(0.5)
                _log("     [modal] Resume card selected — clicking Next", "info")
            except Exception:
                pass

        # Click Next/Submit to advance past the resume selection page
        _modal_click_next(page)
        time.sleep(2)
        return True

    except Exception:
        return False


def _modal_screenshot_b64(page) -> str:
    try:
        raw = page.screenshot(type="jpeg", quality=65, full_page=False)
        return base64.b64encode(raw).decode()
    except Exception:
        return ""


def _modal_elements(page) -> list:
    """Visible interactive elements inside the Easy Apply modal."""
    try:
        return page.evaluate("""() => {
            const MAX = 60;
            const modal = document.querySelector('.jobs-easy-apply-content')
                       || document.querySelector('[role="dialog"]')
                       || document;

            // Returns the most descriptive label text for an element,
            // walking up to 8 ancestors to find fieldset legend or label.
            const getLabel = (el) => {
                if (el.id) {
                    const lbl = document.querySelector(`label[for='${el.id}']`);
                    if (lbl) return lbl.innerText.trim().slice(0, 120);
                }
                const lblId = el.getAttribute('aria-labelledby');
                if (lblId) {
                    const parts = lblId.split(/\\s+/).map(id => {
                        const n = document.getElementById(id);
                        return n ? n.innerText.trim() : '';
                    }).filter(Boolean);
                    if (parts.length) return parts.join(' ').slice(0, 120);
                }
                // aria-label is authoritative when present
                const aria = el.getAttribute('aria-label');
                if (aria) return aria.slice(0, 120);
                let p = el.parentElement;
                for (let i = 0; i < 8 && p; i++, p = p.parentElement) {
                    if (p.tagName === 'LABEL') return p.innerText.trim().slice(0, 120);
                    if (p.tagName === 'FIELDSET') {
                        const leg = p.querySelector('legend');
                        if (leg) return leg.innerText.trim().slice(0, 120);
                    }
                    // LinkedIn wraps questions in <div class="fb-form-element">
                    const heading = p.querySelector('label, legend, h3, h4, [class*="label"]');
                    if (heading && heading !== el) return heading.innerText.trim().slice(0, 120);
                }
                return el.getAttribute('placeholder') || '';
            };

            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0
                    && getComputedStyle(el).display !== 'none'
                    && getComputedStyle(el).visibility !== 'hidden';
            };

            // Detect LinkedIn typeahead / autocomplete inputs
            // These need special handling: type → wait for dropdown → click option
            const isTypeahead = (el) => {
                return (
                    el.getAttribute('role') === 'combobox' ||
                    el.getAttribute('aria-autocomplete') === 'list' ||
                    el.getAttribute('aria-autocomplete') === 'both' ||
                    el.getAttribute('autocomplete') === 'off' && el.getAttribute('aria-expanded') !== null ||
                    el.classList.contains('basic-typeahead__raw-input') ||
                    !!el.closest('[data-js-typeahead-input]') ||
                    !!el.closest('.basic-typeahead')
                );
            };

            const results = [];
            for (const el of modal.querySelectorAll('input, textarea, select, button, label')) {
                if (!isVisible(el)) continue;
                const tag  = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || tag).toLowerCase();
                if (type === 'hidden') continue;

                // Build the most stable selector:
                // Priority: aria-label > id > name > data-test-id > tag
                let sel = tag;
                const ariaLabelAttr = el.getAttribute('aria-label');
                if (el.id && !el.id.includes(':')) {
                    // Only use #id when it has no CSS-special chars like ':'
                    sel = `#${el.id}`;
                } else if (ariaLabelAttr) {
                    // aria-label selectors are stable across LinkedIn A/B tests
                    sel = `${tag}[aria-label='${ariaLabelAttr.replace(/'/g, "\\'")}']`;
                } else if (el.getAttribute('name')) {
                    sel = `${tag}[name='${el.getAttribute('name')}']`;
                } else if (el.getAttribute('data-test-id')) {
                    sel = `[data-test-id='${el.getAttribute('data-test-id')}']`;
                } else if (el.id) {
                    // ID with special chars — use attribute selector
                    sel = `[id='${el.id}']`;
                }

                let options = [];
                if (tag === 'select') {
                    options = Array.from(el.options)
                        .map(o => o.text.trim())
                        .filter(t => t && !['select','select an option','please select','--','select one','choose'].includes(t.toLowerCase()));
                }

                // For radio/checkbox: whether it is currently checked
                const checked = (type === 'radio' || type === 'checkbox') ? el.checked : undefined;

                results.push({
                    selector:    sel,
                    tag,
                    type,
                    label:       getLabel(el),
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel:   ariaLabelAttr || '',
                    // For <select>: show the visible display text, not the raw value attribute.
                    // This lets the LLM correctly identify already-selected options
                    // (e.g. "India (+91)") without needing to know internal option values.
                    currentValue: tag === 'select'
                        ? (el.selectedIndex >= 0 && el.options[el.selectedIndex]
                            ? el.options[el.selectedIndex].text.trim()
                            : '')
                        : (el.value || el.innerText?.trim().slice(0, 80) || ''),
                    checked,
                    required:    el.required || el.getAttribute('aria-required') === 'true',
                    hasError:    !!el.closest('.artdeco-inline-feedback--error, .fb-form-element--error'),
                    isTypeahead: isTypeahead(el),
                    options,
                });
                if (results.length >= MAX) break;
            }
            return results;
        }""")
    except Exception:
        return []


def _safe_locator(page, selector: str):
    """
    Return a Playwright locator that works even when the selector contains
    characters that are special in CSS (e.g. LinkedIn's URN-based IDs which
    contain ':', '(', ')').

    Conversions applied:
      • #id-with-specials  →  [id="id-with-specials"]
      • label:contains('X') →  label:has-text("X")   (jQuery → Playwright)
    """
    # Fix jQuery :contains() → Playwright :has-text()
    selector = re.sub(r":contains\(['\"]?(.*?)['\"]?\)", r':has-text("\1")', selector)

    # If this looks like an ID selector with special CSS characters, use attribute selector
    if selector.startswith("#") and any(c in selector for c in ":()[]|,+~>"):
        raw_id = selector[1:]
        return page.locator(f'[id="{raw_id}"]')

    return page.locator(selector)


def _modal_execute(page, profile: dict, action: dict) -> tuple[bool, str]:
    """
    Execute a GPT action inside the LinkedIn Easy Apply modal.
    Returns (success, error_msg).
    """
    act      = (action.get("action") or "").strip()
    selector = (action.get("selector") or "").strip()
    value    = (action.get("value") or "").strip()

    try:
        if act == "upload_resume":
            resume_path = profile.get("resume_path", "")
            if not resume_path or not os.path.exists(resume_path):
                return (False, "resume_path missing or file not found")
            try:
                fi = page.wait_for_selector("input[type='file']", timeout=3000, state="attached")
                if fi:
                    fi.set_input_files(resume_path)
                    time.sleep(0.8)
                    return (True, "")
                return (False, "No file input found")
            except Exception as e:
                return (False, str(e))

        if not selector:
            return (False, f"No selector for action '{act}'")

        if act == "typeahead":
            # Typeahead/autocomplete inputs: type slowly to trigger suggestions,
            # then click the first matching option or press Enter/ArrowDown.
            try:
                loc = _safe_locator(page, selector).first
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed()
                loc.click()
                page.wait_for_timeout(200)
                # Clear existing value first
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                page.wait_for_timeout(150)
                # Type the search value character by character with small delays
                page.keyboard.type(str(value), delay=60)
                page.wait_for_timeout(900)   # wait for dropdown to populate

                # Try to click the first matching option in the suggestion list
                val_lower = str(value).lower()
                found_option = False
                for opt_sel in [
                    f'[role="option"]:has-text("{value}")',
                    '[role="option"]',
                    f'li[role="listitem"]:has-text("{value}")',
                    '.basic-typeahead__selectable:has-text("{value}")',
                    '.basic-typeahead__selectable',
                ]:
                    try:
                        opt = page.locator(opt_sel).first
                        if opt.count() > 0 and opt.is_visible():
                            opt.click(timeout=2000)
                            page.wait_for_timeout(400)
                            found_option = True
                            break
                    except Exception:
                        continue

                if not found_option:
                    # Press ArrowDown + Enter to select first suggestion
                    page.keyboard.press("ArrowDown")
                    page.wait_for_timeout(300)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(400)

                return (True, "")
            except Exception as e:
                return (False, str(e))

        if act == "fill":
            try:
                loc = _safe_locator(page, selector).first
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed()

                # Special handling for date inputs
                input_type = ""
                try:
                    input_type = (loc.get_attribute("type") or "").lower()
                except Exception:
                    pass

                if input_type == "date":
                    # HTML date inputs require YYYY-MM-DD format
                    date_val = str(value)
                    # If user gave MM/YYYY convert to YYYY-MM-01
                    m = re.match(r"(\d{1,2})/(\d{4})", date_val)
                    if m:
                        date_val = f"{m.group(2)}-{m.group(1).zfill(2)}-01"
                    try:
                        loc.fill(date_val)
                        page.wait_for_timeout(400)
                        return (True, "")
                    except Exception:
                        pass

                # ── Approach 1: keyboard (React-aware) ───────────────────────────
                # click → select-all → type char-by-char → Tab
                # Tab fires onBlur which commits React state for ALL input types,
                # not just number/tel. Must always press Tab.
                loc.click()
                page.keyboard.press("Control+a")
                page.keyboard.type(str(value))
                page.keyboard.press("Tab")   # always — commits React state via onBlur
                page.wait_for_timeout(500)

                # ── Verify approach 1 worked ──────────────────────────────────────
                try:
                    actual = loc.input_value()
                except Exception:
                    actual = str(value)   # can't verify input_value — assume ok

                if actual.strip() != "" and actual.strip() == str(value).strip():
                    return (True, "")   # keyboard approach succeeded

                # ── Approach 2: JS native-setter (React fiber) ───────────────────
                # Sets value via React's internal prototype setter, then fires the
                # full event chain React expects: input → change → blur.
                loc.evaluate("""(el, val) => {
                    el.focus();
                    const proto = el.tagName === 'TEXTAREA'
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                    if (setter) setter.call(el, val);
                    el.dispatchEvent(new InputEvent('input',  { bubbles: true, data: val }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    // React 16/17 fiber props
                    const rk = Object.keys(el).find(
                        k => k.startsWith('__reactProps') || k.startsWith('__reactFiber')
                    );
                    if (rk && el[rk] && el[rk].onChange) {
                        el[rk].onChange({ target: el, currentTarget: el });
                    }
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }""", str(value))
                page.wait_for_timeout(400)

                # ── Verify approach 2 worked ──────────────────────────────────────
                try:
                    actual2 = loc.input_value()
                except Exception:
                    actual2 = str(value)

                if actual2.strip() == "":
                    return (False, f"Value '{value}' did not persist after keyboard+JS fill (React may have rejected it)")

                return (True, "")
            except Exception as e:
                return (False, str(e))

        elif act == "click":
            try:
                loc = _safe_locator(page, selector).first
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed()
                _human_delay(80, 200)

                # ── Radio button special handling ─────────────────────────────
                # LinkedIn radio inputs must be activated via their LABEL —
                # clicking the <input type="radio"> directly does not fire
                # React's onChange and the selection never registers.
                # Strategy:
                #   1. If GPT gave a radio input selector → find the label by
                #      (a) label[for=id], (b) parent label, (c) sibling label
                #      that contains the wanted value text, then click THAT.
                #   2. Fall back to a JS-dispatch that fires both the native
                #      click and React's synthetic event on the input.
                el_type = ""
                try:
                    el_type = (loc.get_attribute("type") or "").lower()
                except Exception:
                    pass

                if el_type == "radio":
                    clicked_radio = False

                    # (a) Try to click a label that wraps or is associated with
                    #     this radio and contains the target value text
                    try:
                        el_id = loc.get_attribute("id") or ""
                        el_name = loc.get_attribute("name") or ""
                        el_val  = loc.get_attribute("value") or value or ""

                        # Look for sibling/parent labels containing the value text
                        candidates = []
                        if el_id:
                            candidates.append(f"label[for='{el_id}']")
                        if el_name and value:
                            candidates.append(
                                f"label:has(input[name='{el_name}'][value='{el_val}'])"
                            )
                        if value:
                            candidates.append(f"label:has-text('{value}')")

                        for lbl_sel in candidates:
                            try:
                                lbl = page.locator(lbl_sel).first
                                if lbl.count() > 0 and lbl.is_visible():
                                    lbl.scroll_into_view_if_needed()
                                    lbl.click(timeout=3000)
                                    page.wait_for_timeout(400)
                                    clicked_radio = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                    # (b) JS fallback: fire click + React synthetic event on input
                    if not clicked_radio:
                        try:
                            loc.evaluate("""(el) => {
                                el.checked = true;
                                el.dispatchEvent(new MouseEvent('click',  { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                const rk = Object.keys(el).find(
                                    k => k.startsWith('__reactProps') || k.startsWith('__reactFiber')
                                );
                                if (rk && el[rk] && el[rk].onChange) {
                                    el[rk].onChange({ target: el, currentTarget: el });
                                }
                            }""")
                            page.wait_for_timeout(400)
                            clicked_radio = True
                        except Exception:
                            pass

                    if clicked_radio:
                        return (True, "")
                    # Fall through to normal click if radio-specific path failed

                # ── Normal click ──────────────────────────────────────────────
                try:
                    loc.click(timeout=4000)
                except Exception:
                    loc.dispatch_event("click")
                page.wait_for_timeout(400)
                return (True, "")
            except Exception as e:
                # Fallback 1: try by visible text if selector looks like plain text
                if not any(c in selector for c in "#.[]:>~+=^$*()|,"):
                    try:
                        page.locator(f"text={selector}").first.click(timeout=2000)
                        return (True, "")
                    except Exception:
                        pass
                # Fallback 2: JS click (bypasses pointer-events:none overlays)
                try:
                    el = page.query_selector(selector)
                    if el:
                        page.evaluate("el => el.click()", el)
                        page.wait_for_timeout(400)
                        return (True, "")
                except Exception:
                    pass
                return (False, str(e))

        elif act == "select":
            try:
                loc = _safe_locator(page, selector).first

                # For truncated IDs: try starts-with match as fallback
                try:
                    loc.wait_for(state="visible", timeout=3000)
                except Exception:
                    if selector.startswith("#") and len(selector) > 20:
                        partial = selector[1:60]
                        loc = page.locator(f'[id^="{partial}"]').first
                        loc.wait_for(state="visible", timeout=3000)

                # Detect element type: native <select> vs LinkedIn custom dropdown
                tag_name = loc.evaluate("el => el.tagName.toLowerCase()")

                if tag_name == "select":
                    # ── Read real options from DOM first ─────────────────────
                    # GPT may return an option text that doesn't exactly match
                    # (e.g. "Prefer not to say" vs "Decline to Self-Identify").
                    # We resolve GPT's answer to the closest REAL option before
                    # attempting any selection — never trust the raw GPT string.
                    real_options: list[str] = loc.evaluate("""el =>
                        Array.from(el.options)
                            .map(o => o.text.trim())
                            .filter(t => t && !['select','select an option',
                                'please select','--','select one','choose',
                                ''].includes(t.toLowerCase()))
                    """)

                    def _best_match(wanted: str, choices: list[str]) -> str | None:
                        if not choices:
                            return None
                        w = wanted.strip().lower()
                        # 1. Exact match
                        for c in choices:
                            if c.strip().lower() == w:
                                return c
                        # 2. GPT answer is substring of option or vice-versa
                        for c in choices:
                            cl = c.strip().lower()
                            if w in cl or cl in w:
                                return c
                        # 3. Word-overlap score
                        stop = {"", "the", "a", "an", "of", "to", "not", "or",
                                "and", "self", "say", "identify", "prefer",
                                "decline", "disclose", "would", "rather"}
                        w_words = set(re.split(r'\W+', w)) - stop
                        best, best_score = None, -1
                        for c in choices:
                            c_words = set(re.split(r'\W+', c.lower())) - stop
                            score = len(w_words & c_words)
                            if score > best_score:
                                best, best_score = c, score
                        return best if best_score > 0 else choices[0]

                    resolved = _best_match(value, real_options) or value
                    if resolved != value:
                        _log(
                            f"     [modal] select resolved '{value}' → '{resolved}' "
                            f"(from {len(real_options)} real options)",
                            "info",
                        )

                    # ── Native <select>: React-aware setter ──────────────────
                    ok = loc.evaluate("""(selectEl, label) => {
                        const opts = Array.from(selectEl.options);
                        const match = opts.find(o =>
                            o.text.trim().toLowerCase() === label.toLowerCase() ||
                            o.text.trim().toLowerCase().includes(label.toLowerCase()) ||
                            label.toLowerCase().includes(o.text.trim().toLowerCase())
                        );
                        if (!match) return false;
                        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
                        setter.call(selectEl, match.value);
                        selectEl.dispatchEvent(new Event('input',  { bubbles: true }));
                        selectEl.dispatchEvent(new Event('change', { bubbles: true }));
                        const pk = Object.keys(selectEl).find(k => k.startsWith('__reactProps'));
                        if (pk && selectEl[pk].onChange) {
                            selectEl[pk].onChange({ target: selectEl, currentTarget: selectEl });
                        }
                        return true;
                    }""", resolved)
                    if ok:
                        page.wait_for_timeout(400)
                        return (True, "")
                    # Standard fallback using the resolved option text
                    try:
                        loc.select_option(label=resolved, timeout=2000)
                        page.wait_for_timeout(400)
                        return (True, "")
                    except Exception:
                        try:
                            loc.select_option(value=resolved, timeout=2000)
                            page.wait_for_timeout(400)
                            return (True, "")
                        except Exception as e2:
                            return (False, f"native select failed for '{resolved}': {e2}")

                else:
                    # ── LinkedIn custom multipleChoice / Workday-style dropdown ──
                    # Pattern: click to open → listbox appears → click matching option
                    try:
                        loc.scroll_into_view_if_needed()
                        loc.click()
                        page.wait_for_timeout(600)
                    except Exception:
                        loc.dispatch_event("click")
                        page.wait_for_timeout(600)

                    # Find matching option in the opened listbox
                    val_lower = value.lower()
                    for opt_sel in [
                        f'[role="option"]:has-text("{value}")',
                        f'li:has-text("{value}")',
                        f'span:has-text("{value}")',
                        f'button:has-text("{value}")',
                    ]:
                        try:
                            opt = page.locator(opt_sel).first
                            if opt.count() > 0:
                                opt.click(timeout=2000)
                                page.wait_for_timeout(400)
                                return (True, "")
                        except Exception:
                            continue

                    # Fallback: find any visible option containing the value text
                    try:
                        opts = page.query_selector_all('[role="option"], li[class*="option"]')
                        for opt in opts:
                            if opt.is_visible() and val_lower in (opt.inner_text() or "").lower():
                                opt.click()
                                page.wait_for_timeout(400)
                                return (True, "")
                    except Exception:
                        pass

                    # Close the dropdown and report failure
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    return (False, f"Custom dropdown option '{value}' not found in opened listbox")

            except Exception as e:
                return (False, str(e))

        else:
            return (False, f"Unknown action: {act}")

    except Exception as e:
        return (False, f"_modal_execute error: {e}")


def _modal_click_next(page) -> bool:
    """Click the Next / Review / Submit button. Returns True if found."""
    for sel in _NAV_SELECTORS:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible() and btn.is_enabled():
                try:
                    btn.scroll_into_view_if_needed()
                except Exception:
                    pass
                _human_delay(100, 300)
                btn.click()
                return True
        except Exception:
            pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Smart-fill helpers — Tier 1 (profile), Tier 2 (cache), Tier 3 (GPT screening)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_cache_key(text: str) -> str:
    """Lowercase + strip punctuation + collapse spaces → stable cache key."""
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_phone_digits(profile: dict) -> str:
    """Return last 10 digits of the candidate's phone number."""
    raw = re.sub(r"\D", "", profile.get("phone", ""))
    return raw[-10:] if len(raw) >= 10 else raw


# ── Profile field patterns ────────────────────────────────────────────────────
# Each tuple: (phrase_to_find_in_label, human_key_desc, value_extractor(profile) → str)
# Ordered from most-specific to least-specific so longer phrases match first.
_PROFILE_FIELD_PATTERNS: list[tuple] = [
    ("first name",            "first_name",         lambda p: ((p.get("full_name") or "").split() or [""])[0]),
    ("last name",             "last_name",           lambda p: " ".join((p.get("full_name") or "").split()[1:]) or ""),
    ("family name",           "last_name",           lambda p: " ".join((p.get("full_name") or "").split()[1:]) or ""),
    ("surname",               "last_name",           lambda p: " ".join((p.get("full_name") or "").split()[1:]) or ""),
    ("full name",             "full_name",           lambda p: p.get("full_name") or ""),
    ("notice period",         "notice_period",       lambda p: str(p.get("notice_period") or "30")),
    ("current ctc",           "current_salary",      lambda p: str(p.get("current_salary") or "")),
    ("current salary",        "current_salary",      lambda p: str(p.get("current_salary") or "")),
    ("current compensation",  "current_salary",      lambda p: str(p.get("current_salary") or "")),
    ("expected ctc",          "expected_salary",     lambda p: str(p.get("expected_salary") or "")),
    ("expected salary",       "expected_salary",     lambda p: str(p.get("expected_salary") or "")),
    ("desired salary",        "expected_salary",     lambda p: str(p.get("expected_salary") or "")),
    # Only "total" / "overall" experience maps to profile — skill-specific questions go to GPT
    ("total years",           "years_of_experience", lambda p: str(int(float(p.get("years_of_experience") or "1")))),
    ("total experience",      "years_of_experience", lambda p: str(int(float(p.get("years_of_experience") or "1")))),
    ("overall experience",    "years_of_experience", lambda p: str(int(float(p.get("years_of_experience") or "1")))),
    ("linkedin",              "linkedin_url",        lambda p: p.get("linkedin_url") or ""),
    ("github",                "github_url",          lambda p: p.get("github_url") or ""),
    ("portfolio",             "portfolio_url",       lambda p: p.get("portfolio_url") or ""),
    ("email",                 "email",               lambda p: p.get("email") or ""),
    # Phone — specific phrases first to avoid matching "phone country code" select
    ("mobile number",         "phone",               _extract_phone_digits),
    ("mobile",                "phone",               _extract_phone_digits),
    ("phone number",          "phone",               _extract_phone_digits),
    ("phone",                 "phone",               _extract_phone_digits),
    # Location — specific first
    ("current city",          "current_city",        lambda p: p.get("current_city") or ""),
    ("current location",      "current_city",        lambda p: p.get("current_city") or ""),
    ("city",                  "current_city",        lambda p: p.get("current_city") or ""),
    ("location",              "current_city",        lambda p: p.get("current_city") or ""),
]


def _match_profile_field(label_lower: str, placeholder_lower: str, profile: dict) -> str | None:
    """
    Check whether an element label matches a known profile field.

    Returns the profile value as a string (possibly empty string) if it's a profile
    field, or None if it should be treated as a screening question.
    """
    combined = f"{label_lower} {placeholder_lower}"
    for phrase, _desc, extractor in _PROFILE_FIELD_PATTERNS:
        if phrase in combined:
            try:
                val = extractor(profile) if callable(extractor) else str(extractor)
                return str(val) if val is not None else ""
            except Exception:
                return ""
    return None


def _values_match(current: str, expected: str) -> bool:
    """
    Return True if the DOM's current value already equals the expected profile value.
    Handles: exact match, digit-only compare (salary/phone), substring (city in full address).
    """
    if not current or not expected:
        return False
    c = current.strip().lower()
    e = expected.strip().lower()
    if c == e:
        return True
    # Digit-only compare — handles salary formatting (8,00,000 vs 800000) and phone
    c_d = re.sub(r"\D", "", c)
    e_d = re.sub(r"\D", "", e)
    if c_d and e_d:
        if c_d == e_d:
            return True
        # Phone: compare last 10 digits
        if len(c_d) >= 10 and len(e_d) >= 10 and c_d[-10:] == e_d[-10:]:
            return True
    # Substring: expected value contained in current (e.g. "Delhi" inside "Delhi, India")
    if e and e in c:
        return True
    return False


def _resolve_selector_from_elements(gpt_sel: str, elements: list) -> str | None:
    """
    Auto-correct a hallucinated GPT selector by word-overlap scoring against the
    real element list.  Returns the best matching real selector, or None.

    Used by both _batch_answer_page and _gpt_answer_screening so they share
    identical correction logic without code duplication.
    """
    known = {e["selector"] for e in elements}
    if gpt_sel in known:
        return gpt_sel

    # Strip CSS special chars to extract the semantic word(s)
    # e.g. "#notice-period" → "notice period",  "[id='ember42']" → "id  ember42"
    raw = re.sub(r"^[#.\['\"]", "", gpt_sel)
    raw = re.sub(r"['\"\]]$", "", raw)
    raw = re.sub(r"[-_]", " ", raw).lower().strip()
    query_words = [w for w in raw.split() if len(w) >= 3]
    if not query_words:
        return None

    best_sel, best_score = None, 0
    for el in elements:
        haystack = " ".join([
            str(el.get("label", "")),
            str(el.get("placeholder", "")),
            str(el.get("name", "")),
        ]).lower()
        score = sum(1 for w in query_words if w in haystack)
        if score > best_score:
            best_score = score
            best_sel = el["selector"]

    return best_sel if best_score > 0 else None


def _detect_page_type(page, elements: list) -> str:
    """
    Classify the current modal page so the main loop can take the fast path
    without wasting a GPT call.

    Returns
    -------
    "review"    — application summary / review page → just click Submit
    "no_inputs" — page has no fillable fields → just click Next
    "normal"    — regular form page with fields to fill
    """
    fillable_count = sum(
        1 for e in elements
        if e.get("tag") in ("input", "textarea", "select")
        and e.get("type") not in ("hidden", "submit", "button", "file")
    )
    if fillable_count > 0:
        return "normal"

    # No fillable inputs — check whether it's a review/submit page
    try:
        body_lower = (page.inner_text("body") or "").lower()
    except Exception:
        body_lower = ""

    _REVIEW_PHRASES = (
        "review your application", "application summary",
        "review application",      "application review",
    )
    if any(ph in body_lower for ph in _REVIEW_PHRASES):
        return "review"

    for sel in (
        "button[aria-label='Submit application']",
        "button:has-text('Submit application')",
    ):
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                return "review"
        except Exception:
            pass

    return "no_inputs"


def _gpt_answer_screening(elements: list, profile: dict) -> list[dict]:
    """
    Ask GPT to answer ONLY the screening questions that couldn't be answered from
    the profile or session cache.

    Sends resume + questions only — no full JD — to minimise token cost.
    Returns a list of validated action dicts (never includes a "next" action).
    """
    if not elements:
        return []

    prompt = f"""You are filling LinkedIn Easy Apply screening questions for a candidate.

=== CANDIDATE RESUME ===
{RESUME_TEXT[:1500]}

=== CANDIDATE QUICK PROFILE ===
Experience       : {profile.get('years_of_experience', '1')} years total
Skills           : {', '.join((profile.get('skills') or [])[:20])}
Notice period    : {profile.get('notice_period', '30')} days
City             : {profile.get('current_city', '')}
Work auth India  : Yes
Visa sponsorship : No

=== SCREENING QUESTIONS (answer only these) ===
{json.dumps(elements, ensure_ascii=False)}

Rules:
- Return a JSON array — one action object per question that needs an answer.
- Copy the "selector" field EXACTLY as it appears in the questions above. Never invent selectors.
- For <select> (action="select"): value MUST exactly match one string from that element's options[].
- For radio buttons (type="radio"): action="click", value = the option label text (e.g. "Yes", "No").
- For numeric / years fields: return only the digit — no units, no surrounding text.
- Authorization / work eligibility in India → "Yes".
- Visa / sponsorship required → "No".
- Skip elements whose currentValue is already correct.
- Do NOT include a "next" action in your output.
- Return ONLY a valid JSON array — no markdown, no code block, no explanation.
"""

    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return ONLY a valid JSON array. No markdown."},
                {"role": "user",   "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
            temperature=0,
        )
        _track_usage(resp)
        raw  = resp.choices[0].message.content.strip()
        data = json.loads(raw)

        if isinstance(data, list):
            actions = data
        else:
            actions = None
            for key in ("actions", "steps", "result", "items"):
                if isinstance(data.get(key), list):
                    actions = data[key]
                    break

        if not actions:
            return []

        # Validate & auto-correct selectors
        known_sels = {e["selector"] for e in elements}
        result: list[dict] = []
        for act in actions:
            if act.get("action") in ("next", "submit", "done"):
                continue
            gpt_sel = str(act.get("selector", ""))
            if gpt_sel and gpt_sel not in known_sels:
                corrected = _resolve_selector_from_elements(gpt_sel, elements)
                if corrected:
                    print(f"     [screening] corrected: {gpt_sel!r} → {corrected!r}")
                    act = {**act, "selector": corrected}
                else:
                    print(f"     [screening] dropped hallucinated selector: {gpt_sel!r}")
                    continue
            result.append(act)

        return result

    except Exception as e:
        print(f"     [screening] GPT call failed: {e}")
        return []


def _smart_fill_page(
    page,
    profile: dict,
    elements: list,
    job_title: str,
    job_description: str,
) -> list[dict] | None:
    """
    Build an optimised action queue for one Easy Apply page.

    Tier 1 — Profile fields  : answered directly from profile.json  (0 GPT tokens)
    Tier 2 — Answer cache    : reuse answers seen in earlier jobs    (0 GPT tokens)
    Tier 3 — GPT screening   : one batch call for the rest           (minimal tokens)

    Special handling baked in:
      • Multi-select checkbox groups (multiple checkboxes sharing one `name`) → skipped.
      • Single consent / agreement checkboxes → auto-ticked.
      • Phone country-code selects → filled with India (+91) from profile.
      • Already-correct fields → skipped (verified against profile / cache).
      • Number inputs → non-digit chars stripped before fill.
    """
    actions:    list[dict] = []
    gpt_needed: list[dict] = []

    # ── Detect multi-select checkbox groups ───────────────────────────────────
    # Checkboxes sharing the same `name` attribute belong to a multi-select group.
    name_counts: dict[str, int] = {}
    for el in elements:
        if el.get("type") == "checkbox":
            n = el.get("name") or ""
            if n:
                name_counts[n] = name_counts.get(n, 0) + 1
    multi_select_names: set[str] = {n for n, c in name_counts.items() if c > 1}

    for el in elements:
        tag      = el.get("tag", "")
        el_type  = el.get("type", "")
        label    = el.get("label", "")
        pholder  = el.get("placeholder", "")
        selector = el.get("selector", "")
        cur_val  = el.get("currentValue", "")
        options  = el.get("options") or []
        name     = el.get("name", "")
        is_ta    = el.get("isTypeahead", False)
        checked  = el.get("checked", False)

        label_lo  = label.lower().strip()
        phld_lo   = pholder.lower().strip()

        # ── Non-fillable types ────────────────────────────────────────────────
        if el_type in ("hidden", "submit", "button", "file"):
            continue
        if tag == "button":
            continue

        # ── Follow-company checkbox — always skip ─────────────────────────────
        if el_type == "checkbox" and "follow" in label_lo:
            continue

        # ── Multi-select checkbox group — skip ────────────────────────────────
        if el_type == "checkbox" and name and name in multi_select_names:
            _log(f"     [smart] Multi-select skip: {label[:60]}", "info")
            continue

        # ── Consent / agreement single checkbox — auto-tick ───────────────────
        if el_type == "checkbox":
            _CONSENT = ("agree", "consent", "terms", "certify", "confirm",
                        "declare", "acknowledge", "accept", "authoriz", "policy")
            if any(kw in label_lo for kw in _CONSENT):
                if not checked:
                    actions.append({
                        "action":   "click",
                        "selector": selector,
                        "value":    "",
                        "reason":   f"Consent: {label[:50]}",
                    })
                continue   # handled regardless of prior state

        # ── Phone country-code select → India (+91) ───────────────────────────
        if tag == "select":
            is_cc = (
                ("country" in label_lo and "code" in label_lo) or
                ("phone"   in label_lo and "country" in label_lo) or
                any(str(o).strip().startswith("+") for o in options[:5])
            )
            if is_cc:
                india_opt = next(
                    (o for o in options if "india" in str(o).lower() or "+91" in str(o)),
                    "+91 India",
                )
                if "india" in cur_val.lower() or "+91" in cur_val:
                    continue   # already correct
                actions.append({
                    "action":   "select",
                    "selector": selector,
                    "value":    india_opt,
                    "reason":   "Phone country code → India (+91)",
                })
                continue

        # ── Tier 1: Profile field ─────────────────────────────────────────────
        profile_val = _match_profile_field(label_lo, phld_lo, profile)
        if profile_val is not None:
            if not profile_val:
                continue    # profile has no value for this field — skip silently

            if _values_match(cur_val, profile_val):
                _log(f"     [smart] T1-skip (already filled): {label[:50]}", "info")
                continue

            _log(f"     [smart] T1-fill: {label[:50]} → {profile_val[:30]}", "info")

            if tag == "select":
                actions.append({"action": "select",    "selector": selector, "value": profile_val, "reason": f"Profile: {label[:40]}"})
            elif is_ta:
                actions.append({"action": "typeahead", "selector": selector, "value": profile_val, "reason": f"Profile: {label[:40]}"})
            else:
                fill_val = profile_val
                if el_type == "number" or "numeric" in selector.lower():
                    fill_val = re.sub(r"[^\d.]", "", fill_val) or fill_val
                actions.append({"action": "fill", "selector": selector, "value": fill_val, "reason": f"Profile: {label[:40]}"})
            continue

        # ── Tier 2: Answer cache ──────────────────────────────────────────────
        cache_key = _normalize_cache_key(label or pholder)
        if cache_key and cache_key in _answer_cache:
            cached = _answer_cache[cache_key]
            if _values_match(cur_val, cached):
                _log(f"     [smart] T2-skip (cache match): {label[:50]}", "info")
                continue

            _log(f"     [smart] T2-fill (cached): {label[:50]} → {cached[:30]}", "info")
            act_type = (
                "select" if tag == "select" else
                "click"  if el_type == "radio" else
                "fill"
            )
            actions.append({"action": act_type, "selector": selector, "value": cached, "reason": f"Cached: {label[:40]}"})
            continue

        # ── Tier 3: Needs GPT ─────────────────────────────────────────────────
        if tag in ("input", "textarea", "select") or el_type == "radio":
            gpt_needed.append(el)

    # ── One GPT call for all remaining screening questions ────────────────────
    if gpt_needed:
        _log(f"     [smart] T3-GPT: {len(gpt_needed)} screening question(s)", "info")
        gpt_actions = _gpt_answer_screening(gpt_needed, profile)

        # Cache non-sensitive GPT answers for future jobs in this session
        _NO_CACHE = ("salary", "ctc", "compensation", "pay", "notice", "expected", "current")
        for act in gpt_actions:
            gpt_sel = act.get("selector", "")
            gpt_val = act.get("value", "")
            if gpt_val:
                for src_el in gpt_needed:
                    if src_el.get("selector") == gpt_sel:
                        el_label = src_el.get("label") or src_el.get("placeholder", "")
                        ck = _normalize_cache_key(el_label)
                        if ck and not any(kw in el_label.lower() for kw in _NO_CACHE):
                            _answer_cache[ck] = gpt_val
                        break
            actions.append(act)

    if not actions and not gpt_needed:
        return None   # nothing to do — caller handles Next click

    # Terminate queue with a navigation action
    actions.append({"action": "next", "selector": "", "value": "", "reason": "All fields processed"})
    return actions


_BATCH_SYSTEM = """You are an expert job application AI. You see ALL the questions on one page of a LinkedIn Easy Apply form.
Your job: return a JSON array of actions that fills EVERY required field on this page optimally for this specific role.

CRITICAL RULES:
- Read the JOB DESCRIPTION carefully. Tailor every answer to impress the hiring manager for THIS specific role.
- For "years of experience" fields: return a whole integer. Check the resume for the specific skill.
  If the skill is on the resume → use actual years. If not → return 0 (be honest, don't inflate).
- For YES/NO questions about skills in the JD: answer YES if the resume shows even adjacent/transferable experience.
- For notice period: always use the candidate's actual notice period in days.
- For salary: use the candidate's CTC values exactly.
- For demographic/optional fields: "Prefer not to say" or "Decline to self-identify".
- Skip "Follow company" checkboxes entirely (do not include them in output).
- End the array with {"action":"next","selector":"","value":"","reason":"All fields filled"}.

SELECTOR RULES (MOST IMPORTANT):
- The "selector" field in EVERY action MUST be copied EXACTLY and VERBATIM from the "selector" key in the FORM ELEMENTS JSON you receive.
- NEVER invent, shorten, simplify, or rewrite a selector. Do NOT use #email, #phone, #city, #name, or any other shorthand — these do not exist in LinkedIn's DOM.
- LinkedIn uses non-semantic IDs like [id='ember342'] or [id='urn:li:...'] — always copy them exactly as given.
- If you cannot find a matching selector in the FORM ELEMENTS list for a field, simply omit that field from your output rather than guessing.

Return ONLY a valid JSON array — no markdown, no code block, no explanation.
Each element: {"action":"fill"|"typeahead"|"click"|"select","selector":"EXACT selector from FORM ELEMENTS list","value":"answer","reason":"why"}
"""


def _batch_answer_page(page, profile: dict, job_title: str,
                       job_description: str, elements: list) -> list[dict] | None:
    """
    Ask GPT to answer ALL questions on this page in ONE call with full JD context.
    Returns a list of action dicts (ending with "next"), or None on failure.
    This is smarter and cheaper than per-field calls because GPT sees the full picture.
    """
    # Only batch if there are actual form fields to fill
    fillable = [
        e for e in elements
        if e.get("tag") in ("input", "textarea", "select")
        and e.get("type") not in ("hidden", "submit", "button", "file")
    ]
    if not fillable:
        return None

    name_parts   = profile.get("full_name", "").split()
    first_name   = name_parts[0] if name_parts else ""
    last_name    = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    phone_raw    = re.sub(r"\D", "", profile.get("phone", ""))
    phone_digits = phone_raw[-10:] if len(phone_raw) >= 10 else phone_raw
    try:
        exp_int = str(max(1, int(float(profile.get("years_of_experience", "1") or "1"))))
    except Exception:
        exp_int = "1"

    prompt = f"""You are filling a LinkedIn Easy Apply form for:
Role: {job_title}

=== JOB DESCRIPTION ===
{job_description[:3000]}

=== CANDIDATE PROFILE ===
Full name: {profile.get('full_name', '')}
First: {first_name}  Last: {last_name}
Email: {profile.get('email', '')}
Phone (digits only): {phone_digits}
City: {profile.get('current_city', '')}
Current role: {profile.get('current_job_title', '')} at {profile.get('current_company', '')}
Total experience: {exp_int} years
Skills: {', '.join(profile.get('skills', [])[:25])}
Notice period: {profile.get('notice_period', '30')} days
Current CTC: {profile.get('current_salary', '')}
Expected CTC: {profile.get('expected_salary', '')}
LinkedIn: {profile.get('linkedin_url', '')}
GitHub: {profile.get('github_url', '')}

=== RESUME (first 1200 chars) ===
{RESUME_TEXT[:1200]}

=== FORM ELEMENTS (ALL questions on this page) ===
{json.dumps(fillable, ensure_ascii=False)}

Instructions:
- Answer EVERY element above that is empty or needs a value.
- Tailor answers to make the candidate look ideal for THIS specific role.
- For skills mentioned in the JD that are also in the resume → give positive/experienced answers.
- For skills NOT in the resume → answer honestly (0 years, No, etc.).
- Elements with a non-empty currentValue that looks correct → skip them (don't include in output).
- End with the "next" action.
"""

    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _BATCH_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=1500,
            temperature=0,
        )
        _track_usage(resp)
        raw = resp.choices[0].message.content.strip()

        # ── Robust JSON parsing with truncation recovery ──────────────────
        # If GPT hit the token limit mid-response the JSON is truncated.
        # Try to salvage the actions already written before the cut-off.
        parsed = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Attempt to extract the partial array before truncation
            try:
                # Find last complete object ending with }
                last_close = raw.rfind("},")
                if last_close == -1:
                    last_close = raw.rfind("}")
                if last_close > 0:
                    partial = raw[:last_close + 1]
                    # Wrap into a valid array
                    bracket = partial.find("[")
                    if bracket != -1:
                        partial = partial[bracket:] + "]"
                    else:
                        partial = "[" + partial + "]"
                    actions_partial = json.loads(partial)
                    # Append a "next" action so the partial batch still terminates cleanly
                    actions_partial.append(
                        {"action": "next", "selector": "", "value": "",
                         "reason": "Recovered from truncated batch response"}
                    )
                    print(f"     [batch] Recovered {len(actions_partial)-1} actions from truncated JSON")
                    return actions_partial
            except Exception:
                pass
            print(f"     [batch] GPT batch call failed: {e}")
            return None

        if isinstance(parsed, list):
            actions = parsed
        else:
            actions = None
            for key in ("actions", "steps", "result", "items"):
                if key in parsed and isinstance(parsed[key], list):
                    actions = parsed[key]
                    break

        if actions is None:
            return None

        # ── Selector auto-correction ──────────────────────────────────────────
        # Delegate to the shared module-level helper so the logic is identical
        # across _batch_answer_page, _gpt_answer_screening, and any future callers.
        validated: list[dict] = []
        for act in actions:
            if act.get("action") in ("next", "submit"):
                validated.append(act)
                continue

            gpt_sel  = str(act.get("selector", ""))
            resolved = _resolve_selector_from_elements(gpt_sel, fillable)

            if resolved is None:
                print(f"     [batch] dropped hallucinated selector: {gpt_sel!r} (no match in DOM)")
                continue

            if resolved != gpt_sel:
                print(f"     [batch] corrected selector: {gpt_sel!r} → {resolved!r}")
                act = {**act, "selector": resolved}

            validated.append(act)

        return validated if validated else None

    except Exception as e:
        print(f"     [batch] GPT batch call failed: {e}")
        return None


def handle_easy_apply_modal(page, profile: dict,
                             job_title: str = "", job_description: str = "") -> str:
    """
    LinkedIn Easy Apply — vision-driven multi-step filler.

    Each step:
      1. Screenshot the modal
      2. Ask GPT what to fill or click
      3. Execute the action
      4. On failure: retry with error context (max 3 failures per action)
      5. When GPT returns "next": click the navigation button
      6. Stop on success toast or after max steps
    """
    name_parts   = profile.get("full_name", "").split()
    first_name   = name_parts[0] if name_parts else ""
    last_name    = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    phone_raw    = re.sub(r"\D", "", profile.get("phone", ""))
    phone_digits = phone_raw[-10:] if len(phone_raw) >= 10 else phone_raw

    tried:                  dict[tuple, int] = {}   # (act, sel, val) → failure count only
    action_counts:          dict[tuple, int] = {}   # loop guard
    last_error:             str              = ""
    consecutive_fails:      int              = 0
    consecutive_next:       int              = 0    # how many times "next" was clicked in a row
    resume_handled_count:   int              = 0   # guard against infinite resume-page loops
    MAX_STEPS                               = 50
    MAX_CONSEC                              = 3

    # Per-page batch action queue:
    # When we land on a NEW page (after "next"), call _batch_answer_page once to
    # get ALL actions for that page in one JD-aware GPT call.  We then execute
    # them from the queue.  If a queued action fails we fall back to per-step GPT.
    page_action_queue: list[dict] = []
    last_page_fingerprint: str   = ""   # tracks which page the queue was built for

    for step in range(1, MAX_STEPS + 1):

        if _modal_is_success(page):
            _log("     [modal] Application submitted!", "success")
            _screenshot(page)
            return "applied"

        # ── Resume selection fast-path — no GPT needed ────────────────────────
        if _handle_resume_selection(page, profile):
            resume_handled_count += 1
            _log(f"     [modal] Resume selection handled ({resume_handled_count}×)", "info")
            if resume_handled_count > 3:
                _log("     [modal] Resume selection page stuck — skipping job", "warning")
                return "skipped"
            tried.clear()
            action_counts.clear()
            last_error = ""
            consecutive_fails = 0
            page_action_queue.clear()
            continue

        # Check modal still open
        modal = page.query_selector(".jobs-easy-apply-content, [role='dialog']")
        if not modal:
            _log("     [modal] Modal closed", "info")
            break

        elements = _modal_elements(page)

        # ── Page type fast-path ───────────────────────────────────────────────
        # Detect review/summary pages and no-input pages before any GPT call.
        page_type = _detect_page_type(page, elements)
        if page_type in ("review", "no_inputs"):
            _log(
                f"     [modal] {'Review/submit' if page_type == 'review' else 'No-input'} "
                f"page — clicking Next/Submit directly",
                "info",
            )
            _modal_click_next(page)
            time.sleep(2.5)
            page_action_queue.clear()
            last_page_fingerprint = ""
            consecutive_next += 1
            if consecutive_next >= 5:
                _log("     [modal] Stuck in no-input loop — skipping job", "warning")
                return "skipped"
            continue

        # Real page with fillable fields — reset no-input counter
        consecutive_next = 0

        # ── Compute page fingerprint to detect when we land on a NEW page ─────
        current_fp = "|".join(
            e.get("selector", "")[:40] + e.get("label", "")[:20]
            for e in elements
        )

        # If the page changed (navigation happened), rebuild the action queue
        if current_fp != last_page_fingerprint and not last_error:
            last_page_fingerprint = current_fp

            # ── Smart fill: Tier 1 (profile) → Tier 2 (cache) → Tier 3 (GPT) ──
            if consecutive_fails == 0:
                batch = _smart_fill_page(
                    page, profile, elements, job_title, job_description
                )
                if batch:
                    page_action_queue = batch
                    _log(
                        f"     [modal] Smart fill: {len(batch)} actions for this page "
                        f"(T1/T2 = no-GPT, T3 = screening only)",
                        "info",
                    )

        # ── Pull next action from queue (if available and not in recovery mode) ─
        if page_action_queue and consecutive_fails == 0 and not last_error:
            action = page_action_queue.pop(0)
            act    = (action.get("action") or "").strip()
            sel    = (action.get("selector") or "").strip()
            val    = (action.get("value") or "").strip()
            reason = (action.get("reason") or "")
            _log(
                f"     [modal] Step {step} [batch]: {act} | {sel[:70]} | {val[:40]} — {reason}",
                "info",
            )
            _screenshot(page)

            # Handle terminal batch actions inline
            if act == "done":
                if _modal_is_success(page):
                    return "applied"
                return "applied"

            if act == "next":
                # Skip the nav action from the queue — let the main next-handler do it
                # by putting "next" back and falling through to the per-step GPT path
                # Actually: just execute it directly here
                pre_fp = current_fp
                clicked = _modal_click_next(page)
                if clicked:
                    _log(f"     [modal] [batch] Navigation button clicked", "info")
                    time.sleep(2.5)
                    post_els = _modal_elements(page)
                    post_fp = "|".join(
                        e.get("selector", "")[:40] + e.get("label", "")[:20]
                        for e in post_els
                    )
                    if post_fp != pre_fp or _modal_is_success(page):
                        tried.clear()
                        action_counts.clear()
                        last_error = ""
                        consecutive_fails = 0
                        page_action_queue.clear()   # old queue is for old page
                    else:
                        consecutive_next += 1
                        page_action_queue.clear()
                        last_error = (
                            "Next was clicked but the page did NOT advance. "
                            "Look for unfilled required fields or validation errors."
                        )
                        consecutive_fails = 2   # force vision on next fallback step
                        if consecutive_next >= 5:
                            return "skipped"
                continue

            # Execute the queued action (non-nav)
            if act == "upload_resume":
                ok, error = _modal_execute(page, profile, action)
                if not ok:
                    # Upload failure: skip this action, keep rest of queue
                    _log(f"     [modal] Batch upload failed: {error} — skipping", "warning")
                continue

            # Skip follow-company
            if act == "click" and "follow" in sel.lower():
                continue

            # ── Validate selector exists in DOM before executing ──────────────
            # Batch GPT sometimes hallucinates IDs that don't exist. Check first
            # so a bad selector doesn't abort the whole queue.
            if sel:
                known_selectors = [e.get("selector", "") for e in elements]
                sel_known = (
                    sel in known_selectors or
                    any(sel[:50] in ks or ks[:50] in sel for ks in known_selectors)
                )
                if not sel_known:
                    # Selector not in DOM — skip this queued action silently
                    _log(
                        f"     [modal] Batch selector not in DOM, skipping: {sel[:60]}",
                        "warning",
                    )
                    continue

            # Execute field action
            _human_delay(150, 450)
            target_label = ""
            try:
                for _el in elements:
                    if _el.get("selector", "") == sel or sel[:40] in _el.get("selector", ""):
                        target_label = _el.get("label", "")[:50]
                        break
            except Exception:
                pass

            ok, error = _modal_execute(page, profile, action)

            if ok:
                consecutive_fails = 0
                last_error = ""
                _human_delay(250, 600)
                loop_key = (act, sel, val, target_label)
                action_counts[loop_key] = action_counts.get(loop_key, 0) + 1
                if action_counts[loop_key] >= 4:
                    _log(f"     [modal] Loop guard fired on batch action — falling back to per-step", "warning")
                    page_action_queue.clear()
                    action_counts.clear()
            else:
                # Single batch action failed — skip it, keep the rest of the queue.
                # Only abort the queue after 3 consecutive batch failures.
                consecutive_fails += 1
                _log(
                    f"     [modal] Batch action FAILED ({consecutive_fails}×): {error} — skipping action",
                    "warning",
                )
                tried[(act, sel, val)] = tried.get((act, sel, val), 0) + 1
                if consecutive_fails >= MAX_CONSEC:
                    _log(
                        f"     [modal] {MAX_CONSEC} consecutive batch failures — switching to per-step GPT",
                        "warning",
                    )
                    page_action_queue.clear()
                    last_error = error
                    consecutive_fails = 0   # reset so per-step starts clean

            continue

        # ── Per-step GPT fallback (also used when queue is empty or in error recovery) ─
        elements_json = json.dumps(elements, ensure_ascii=False)

        error_note = (
            f"\n⚠ Last action FAILED: {last_error}\nTry a different selector or method.\n"
            if last_error else ""
        )
        tried_note = ""
        if tried:
            lines = "\n".join(
                f"  - action={a!r} selector={s!r} value={v!r} (tried {c}×)"
                for (a, s, v), c in tried.items()
            )
            tried_note = f"\nAlready tried — do NOT repeat any of these (even if they 'succeeded'):\n{lines}\n"

        # Integer experience for LLM (never decimal — LinkedIn numeric fields require integers)
        try:
            exp_int = str(max(1, int(float(profile.get("years_of_experience", "1") or "1"))))
        except Exception:
            exp_int = "1"

        jd_snippet = ""
        if job_description:
            jd_snippet = f"\nJob being applied for: {job_title}\nJD summary:\n{job_description[:1500]}\n"

        candidate_text = (
            f"Step {step}/{MAX_STEPS}\n\n"
            f"Candidate profile:\n"
            f"  Full name          : {profile.get('full_name', '')}\n"
            f"  First name         : {first_name}\n"
            f"  Last name          : {last_name}\n"
            f"  Email              : {profile.get('email', '')}\n"
            f"  Phone digits       : {phone_digits}  ← ONLY these digits, no country code\n"
            f"  City               : {profile.get('current_city', '')}\n"
            f"  Job title          : {profile.get('current_job_title', '')}\n"
            f"  Current company    : {profile.get('current_company', '')}\n"
            f"  Total experience   : {exp_int} years  ← USE THIS INTEGER for any 'years of experience' field\n"
            f"  Skills             : {', '.join(profile.get('skills', [])[:20])}\n"
            f"  Notice period      : {profile.get('notice_period', '30')} days\n"
            f"  Current CTC        : {profile.get('current_salary', '')}\n"
            f"  Expected CTC       : {profile.get('expected_salary', '')}\n"
            f"  LinkedIn URL       : {profile.get('linkedin_url', '')}\n"
            f"  GitHub URL         : {profile.get('github_url', '')}\n"
            f"  Employed           : Yes\n"
            f"  Sponsorship needed : No\n"
            f"  Work authorized    : Yes\n\n"
            f"Resume text (first 1000 chars):\n{RESUME_TEXT[:1000]}\n"
            f"{jd_snippet}"
            f"{error_note}"
            f"{tried_note}\n"
            f"IMPORTANT: Each element below has a 'currentValue' field showing what is already filled.\n"
            f"If currentValue is correct, SKIP that field and move to the next empty required one.\n\n"
            f"Modal elements (DOM):\n{elements_json}"
        )

        # ── Step 1: DOM-only call (no vision — cheaper) ───────────────────────
        # ── Step 2: Vision fallback if stuck (2+ consecutive failures) ────────
        use_vision = consecutive_fails >= 2
        if use_vision:
            screenshot_b64 = _modal_screenshot_b64(page)
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
            _log(f"     [modal] Step {step}: using vision fallback (stuck)", "warning")
        else:
            user_content = candidate_text

        try:
            resp = _openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _MODAL_VISION_SYSTEM},
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
                wait_sec = 2.0
                ms_match = re.search(r"try again in (\d+)ms", err_str, re.IGNORECASE)
                s_match  = re.search(r"try again in ([\d.]+)s", err_str, re.IGNORECASE)
                if ms_match:
                    wait_sec = max(1.0, int(ms_match.group(1)) / 1000 + 0.5)
                elif s_match:
                    wait_sec = max(1.0, float(s_match.group(1)) + 0.5)
                _log(f"     [modal] Rate limited — waiting {wait_sec:.1f}s before retry", "warning")
                time.sleep(wait_sec)
                continue  # Don't count as a failure
            _log(f"     [modal] GPT error at step {step}: {e}", "warning")
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSEC:
                break
            continue

        act    = (action.get("action") or "").strip()
        sel    = (action.get("selector") or "").strip()
        val    = (action.get("value") or "").strip()
        reason = (action.get("reason") or "")

        _log(f"     [modal] Step {step}: {act} | {sel[:70]} | {val[:40]}  — {reason}", "info")
        _screenshot(page)

        # ── Terminal: submit / next / done ───────────────────────────────────────
        if act == "done":
            if _modal_is_success(page):
                return "applied"
            # Treat as applied if GPT is confident
            return "applied"

        if act == "next":
            # Snapshot page selector fingerprint before clicking so we can tell
            # whether the page actually advanced after the click.
            pre_fingerprint = ""
            try:
                pre_els = _modal_elements(page)
                pre_fingerprint = "|".join(
                    e.get("selector", "") + e.get("label", "")[:30]
                    for e in pre_els
                )
            except Exception:
                pass

            clicked = _modal_click_next(page)
            if clicked:
                _log(f"     [modal] Navigation button clicked", "info")
                time.sleep(2.5)

                # Check whether the page actually changed
                post_fingerprint = ""
                try:
                    post_els = _modal_elements(page)
                    post_fingerprint = "|".join(
                        e.get("selector", "") + e.get("label", "")[:30]
                        for e in post_els
                    )
                except Exception:
                    pass

                page_advanced = (post_fingerprint != pre_fingerprint) or _modal_is_success(page)

                if page_advanced:
                    # Real advance — reset all state
                    tried.clear()
                    action_counts.clear()
                    last_error = ""
                    consecutive_fails = 0
                    consecutive_next = 0
                else:
                    # Button clicked but page didn't move — collect any error text
                    consecutive_next += 1
                    error_texts: list[str] = []
                    try:
                        err_els = page.query_selector_all(
                            ".artdeco-inline-feedback--error, "
                            ".fb-form-element__error-field, "
                            "[data-test-inline-error]"
                        )
                        error_texts = [
                            (el.inner_text() or "").strip()
                            for el in err_els
                            if el.is_visible() and (el.inner_text() or "").strip()
                        ]
                    except Exception:
                        pass

                    if error_texts:
                        last_error = (
                            f"Next clicked but form has validation errors: "
                            f"{'; '.join(error_texts[:5])}. Fix these errors first."
                        )
                    else:
                        last_error = (
                            "Next was clicked but the page did NOT advance. "
                            "Look for: (1) unfilled required fields, "
                            "(2) unchecked agreement/consent checkboxes, "
                            "(3) a 'Follow company' checkbox that must be ticked, "
                            "(4) a radio button group with no selection. "
                            "Fill or click whatever is blocking submission."
                        )

                    # Force vision on next call so LLM can actually see the page
                    consecutive_fails = 2

                    if consecutive_next >= 5:
                        _log(
                            f"     [modal] Stuck in next-click loop "
                            f"({consecutive_next}×) — skipping job",
                            "warning",
                        )
                        try:
                            page.locator("button[aria-label='Dismiss']").first.click()
                        except Exception:
                            pass
                        return "skipped"

            else:
                _log(f"     [modal] No nav button found on step {step}", "warning")
                consecutive_next = 0
                consecutive_fails += 1
                if consecutive_fails >= MAX_CONSEC:
                    break
            continue

        if act == "upload_resume":
            ok, error = _modal_execute(page, profile, action)
            if ok:
                consecutive_fails = 0
                last_error = ""
                time.sleep(1)
            else:
                last_error = error
                consecutive_fails += 1
            continue

        # ── Auto-skip "Follow company" checkbox — never block on it ─────────────
        if act == "click" and "follow" in sel.lower():
            _log(f"     [modal] Auto-skipping follow-company checkbox", "info")
            continue
        # Also skip if the label text says "follow"
        follow_label = (action.get("reason") or "").lower()
        if act == "click" and "follow" in follow_label and "company" in follow_label:
            _log(f"     [modal] Auto-skipping follow-company click", "info")
            continue

        # ── Regular field action ─────────────────────────────────────────────────
        consecutive_next = 0   # a real action broke the next-click chain
        _human_delay(150, 500)   # human-like pause before each action

        # Get the label of the target element BEFORE executing the action.
        # LinkedIn reuses the SAME selector for multiple sequential questions —
        # only the label changes.  Including label in the loop key means
        # ("fill", sel, "0", "Program design years") and
        # ("fill", sel, "0", "Women empowerment years") are separate counters,
        # so filling "0" for many different questions never triggers a false skip.
        target_label = ""
        try:
            cur_els = _modal_elements(page)
            for _el in cur_els:
                if _el.get("selector", "") == sel:
                    target_label = _el.get("label", "")[:50]
                    break
                # Partial match for truncated IDs
                if sel and sel[:40] in _el.get("selector", ""):
                    target_label = _el.get("label", "")[:50]
        except Exception:
            pass

        ok, error = _modal_execute(page, profile, action)
        fail_key = (act, sel, val)   # failure counter key

        if ok:
            consecutive_fails = 0
            last_error = ""
            _human_delay(300, 700)   # human-like pause after successful action

            # Loop key includes label so different questions on the same element
            # are never conflated, even when selector and value are identical.
            loop_key = (act, sel, val, target_label)
            action_counts[loop_key] = action_counts.get(loop_key, 0) + 1
            if action_counts[loop_key] >= 4:
                _log(
                    f"     [modal] '{act}' on '{sel[:60]}' label='{target_label[:30]}' "
                    f"(val='{val}') repeated 4× with no advance — skipping job",
                    "warning",
                )
                try:
                    page.locator("button[aria-label='Dismiss']").first.click()
                except Exception:
                    pass
                return "skipped"

        else:
            # Only failed attempts count toward the skip threshold
            tried[fail_key] = tried.get(fail_key, 0) + 1
            last_error = error
            consecutive_fails += 1

            _log(f"     [modal] Step {step} FAILED ({tried[fail_key]}×): {error}", "warning")

            if tried[fail_key] >= MAX_CONSEC:
                _log(f"     [modal] Action failed {MAX_CONSEC}× — skipping job", "warning")
                try:
                    page.locator("button[aria-label='Dismiss']").first.click()
                except Exception:
                    pass
                return "skipped"

            if consecutive_fails >= MAX_CONSEC:
                _log(f"     [modal] {MAX_CONSEC} consecutive failures — skipping job", "warning")
                try:
                    page.locator("button[aria-label='Dismiss']").first.click()
                except Exception:
                    pass
                return "skipped"

    # Close modal if still open
    try:
        page.locator("button[aria-label='Dismiss']").first.click()
    except Exception:
        pass

    return "skipped"


###  old helpers removed — vision loop handles everything  ###
# ---------------------------------------------------------------------------
# Per-job apply — START (scroll down)


# ---------------------------------------------------------------------------
# Per-job apply
# ---------------------------------------------------------------------------

def get_job_description(page) -> str:
    """Extract full job description text from the current job page."""
    for sel in [
        ".jobs-description-content__text",
        ".jobs-description__content",
        ".job-details-jobs-unified-top-card__job-insight",
        "#job-details",
        ".description__text",
    ]:
        try:
            el = page.query_selector(sel)
            if el:
                txt = el.inner_text().strip()
                if len(txt) > 100:
                    return txt
        except Exception:
            continue
    # Fallback: grab all visible paragraph text
    try:
        return page.evaluate("""
            () => Array.from(document.querySelectorAll('p, li'))
                       .map(e => e.innerText.trim())
                       .filter(t => t.length > 20)
                       .join('\\n')
        """)
    except Exception:
        return ""


def is_good_fit(job: dict, description: str) -> tuple[bool, str]:
    """
    Decide whether to apply to a job.

    Decision hierarchy
    ──────────────────
    1. Fast path — if the job title contains any keyword from the user's
       search query, always apply.  The user explicitly said they want this
       role; we must not override that intent.
    2. Slow path (GPT) — for titles that don't match the query, estimate the
       candidate's skill overlap with the JD.  Skip ONLY when overlap < 30 %.
       All other reasons (seniority, category, etc.) are ignored.
    """
    # ── Fast path: title matches the user's search query ─────────────────────
    # Split on commas, pipes, slashes and spaces so "AIML Engineer, Data Scientist"
    # becomes ["AIML", "Engineer", "Data", "Scientist"].
    query_terms = [
        t.strip().lower()
        for t in re.split(r"[,|/\s]+", JOB_SEARCH_QUERY)
        if len(t.strip()) > 2
    ]
    title_lower = job["title"].lower()
    matching = [t for t in query_terms if t in title_lower]
    if matching:
        return True, f"Title matches your search query ('{', '.join(matching)}')"

    # ── Slow path: GPT skill-overlap check ───────────────────────────────────
    prompt = f"""You are a recruiter screening a job application.

The user is searching for: "{JOB_SEARCH_QUERY}"

Candidate's resume summary:
{RESUME_TEXT[:1500]}

Job Title   : {job['title']}
Company     : {job['company']}
Description : {description[:2000]}

Your only task: estimate what percentage of the job's REQUIRED skills the
candidate already has based on their resume.

Rules — apply strictly in order:
1. Count only skills the JD lists as required or strongly preferred.
2. A skill counts if the candidate's resume shows it or a close equivalent.
3. SKIP (NO) only if the candidate has fewer than 30 % of required skills.
4. For ALL other cases return YES — do NOT reject on title, seniority, or
   role category. The user chose this search query deliberately.

Reply in exactly this format (2 lines, nothing else):
DECISION: YES or NO
REASON: one sentence — state the approximate skill overlap percentage
"""
    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=80,
        )
        _track_usage(resp)
        text = resp.choices[0].message.content.strip()
        decision = "YES" in text.split("\n")[0].upper()
        reason = ""
        for line in text.split("\n"):
            if line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[-1].strip()
                break
        if not reason:
            reason = text
        return decision, reason
    except Exception as e:
        return True, f"API error ({e}) — applying anyway"


def apply_to_job(page, job: dict, index: int, profile: dict) -> str:
    try:
        job_url = job["url"]
        title   = job.get("title", "Unknown")
        company = job.get("company", "Unknown")

        print(f"\n[{index}] {title} @ {company}")
        print(f"     Location : {job.get('location', '')}")
        print(f"     URL      : {job_url}")

        # ── Navigate via search split-pane (NOT direct /jobs/view/ URL) ────────
        #
        # LinkedIn renders two completely different page layouts:
        #   • /jobs/view/ID/  → standalone page; apply button often absent in headless
        #   • /jobs/search/?currentJobId=ID  → split-pane; button always in DOM
        #
        # We use the split-pane URL so the Easy Apply button is reliably rendered.
        job_id = job_url.rstrip("/").split("/")[-1]
        pane_url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={JOB_SEARCH_QUERY.replace(' ', '%20')}"
            f"&location={JOB_LOCATION.replace(' ', '%20')}"
            f"&currentJobId={job_id}"
        )
        if EASY_APPLY_ONLY:
            pane_url += "&f_AL=true"

        try:
            page.goto(pane_url, wait_until="load", timeout=30000)
        except Exception:
            pass

        # Wait for the job detail panel on the right side to render
        _DETAIL_PANEL_WAIT = (
            ".jobs-search__job-details, "
            ".job-view-layout, "
            ".jobs-details__main-content, "
            ".jobs-description-content__text, "
            "#job-details"
        )
        try:
            page.wait_for_selector(_DETAIL_PANEL_WAIT, timeout=12000)
        except Exception:
            pass

        # Scroll slightly to trigger lazy-loaded button rendering, then scroll back
        page.evaluate("window.scrollTo(0, 200)")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(4)   # allow React to finish rendering the apply button

        _screenshot(page)   # capture split-pane job detail

        # Extract description and ask AI if this is a good fit
        description = get_job_description(page)
        fit, reason = is_good_fit(job, description)

        if not fit:
            _log(f"[{index}] {title} @ {company} — Skipped: {reason}", "warning")
            _send_company(index, title, company, job.get("location", ""),
                          "skipped", reason, description, job_url)
            return "skipped"

        _log(f"[{index}] {title} @ {company} — Good fit: {reason}", "found")

        # Check if already applied
        for sel in [
            "text=Applied",
            ".jobs-s-apply__application-link--applied",
            "button[aria-label*='Applied']",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    _log(f"[{index}] {title} @ {company} — Already applied", "info")
                    _send_company(index, title, company, job.get("location", ""),
                                  "already_applied", "Already applied", description, job_url)
                    return "already_applied"
            except Exception:
                continue

        # ── Dismiss any Premium / promotional overlay ────────────────────────
        for dismiss_sel in [
            "button[aria-label*='Dismiss']",
            "button[aria-label*='dismiss']",
            ".artdeco-modal__dismiss",
            "[data-test-modal-close-btn]",
        ]:
            try:
                el = page.query_selector(dismiss_sel)
                if el:
                    el.click()
                    time.sleep(0.4)
            except Exception:
                pass

        # ── Locate and click the Easy Apply button ───────────────────────────
        #
        # In LinkedIn's split-pane view there are TWO "Easy Apply" buttons:
        #   • LEFT panel  — the job card in the search list (opens a mini-preview)
        #   • RIGHT panel — the job detail card (opens the full application modal)
        #
        # We must target only the RIGHT panel button.  Right-panel containers:
        #   .jobs-search__job-details  /  .job-view-layout  /  .jobs-details
        #
        # After clicking we confirm the modal with wait_for_selector (not just
        # query_selector) to handle async rendering delays.

        # Right-side detail panel containers (comma-separated for CSS selectors)
        _DETAIL_PANEL = ".jobs-search__job-details, .job-view-layout, .jobs-details, .jobs-details__main-content"

        # Modal selectors — broad enough to survive minor LinkedIn HTML changes
        _MODAL_SELECTOR = (
            ".jobs-easy-apply-content, "
            ".jobs-easy-apply-modal, "
            "[data-test-modal-id='easy-apply-modal'], "
            "[data-test-modal='easy-apply-modal'], "
            ".artdeco-modal[role='dialog']"
        )

        def _find_and_click_easy_apply(pg) -> bool:
            """
            Tries up to 5 times to click the Easy Apply button inside the
            right-side detail panel and confirm the application modal appeared.
            Returns True on success, False if all attempts fail.
            """
            for attempt in range(5):
                pg.evaluate("window.scrollTo(0, 0)")
                time.sleep(0.6)

                # ── Step 1: find the button scoped to the detail panel ────────
                btn_info = pg.evaluate("""
                    () => {
                        const PANEL_SEL = [
                            '.jobs-search__job-details',
                            '.job-view-layout',
                            '.jobs-details',
                            '.jobs-details__main-content',
                            '.scaffold-layout__detail',
                        ];
                        const panel = PANEL_SEL.reduce(
                            (found, s) => found || document.querySelector(s), null
                        );
                        const scope = panel || document;

                        const EXCLUDED = ['save', 'dismiss', 'follow', 'share', 'report',
                                          'message', 'connect', 'see more', 'show more'];
                        const isApplyBtn = b => {
                            if (!b.offsetParent) return false;  // not visible
                            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                            const text = (b.innerText || '').trim().toLowerCase();
                            if (EXCLUDED.some(w => text === w || aria === w)) return false;
                            if (text === '' && aria === '') return false;
                            return (
                                aria.includes('easy apply') || text.includes('easy apply') ||
                                aria === 'apply'            || text === 'apply'            ||
                                aria.startsWith('apply to') || text.startsWith('apply to') ||
                                aria.includes('apply now')  || text.includes('apply now')  ||
                                aria.includes('apply on')   || text.includes('apply on')   ||
                                text.startsWith('apply')    || aria.startsWith('apply')
                            );
                        };

                        // Also check anchor tags that look like apply buttons
                        const allCandidates = [
                            ...Array.from(scope.querySelectorAll('button')),
                            ...Array.from(scope.querySelectorAll('a[href*="apply"]')),
                        ];

                        // Prefer Easy Apply first
                        const easyBtn = allCandidates.find(b => {
                            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                            const text = (b.innerText || '').trim().toLowerCase();
                            return aria.includes('easy apply') || text.includes('easy apply');
                        });
                        const btn = easyBtn || allCandidates.find(isApplyBtn);
                        if (!btn) return null;

                        btn.scrollIntoView({ behavior: 'instant', block: 'center' });

                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const text = (btn.innerText || '').trim().toLowerCase();
                        return {
                            ariaLabel:   btn.getAttribute('aria-label') || '',
                            text:        (btn.innerText || '').trim(),
                            className:   btn.className || '',
                            tagName:     btn.tagName,
                            inPanel:     panel !== null,
                            isEasyApply: aria.includes('easy apply') || text.includes('easy apply'),
                        };
                    }
                """)

                if not btn_info:
                    _log(f"[{index}] Attempt {attempt + 1}: Apply button not found in DOM", "warning")
                    # On odd attempts, try scrolling the page to trigger lazy rendering
                    if attempt % 2 == 0:
                        pg.evaluate("window.scrollTo(0, 400)")
                        time.sleep(1)
                        pg.evaluate("window.scrollTo(0, 0)")
                    time.sleep(2.5)
                    continue

                time.sleep(0.4)   # let scrollIntoView settle

                # ── Step 2: Playwright real click (force=True bypasses visibility) ──
                clicked = False

                # Build ordered selector list — prefer the scoped panel selector
                candidate_selectors = []
                if btn_info.get("ariaLabel"):
                    aria_esc = btn_info["ariaLabel"].replace("'", "\\'")
                    candidate_selectors.append(f"button[aria-label='{aria_esc}']")
                if btn_info.get("text"):
                    candidate_selectors.append(f"button:has-text('{btn_info['text']}')")

                # Scoped selectors (right panel only) then global fallbacks
                _PANELS = [
                    ".jobs-search__job-details",
                    ".job-view-layout",
                    ".jobs-details",
                    ".jobs-details__main-content",
                    ".scaffold-layout__detail",
                ]
                for panel in _PANELS:
                    candidate_selectors += [
                        f"{panel} button[aria-label*='Easy Apply']",
                        f"{panel} button:has-text('Easy Apply')",
                        f"{panel} .jobs-apply-button--top-card",
                        f"{panel} button.jobs-apply-button",
                        f"{panel} button[aria-label='Apply']",
                        f"{panel} button[aria-label*='Apply now']",
                        f"{panel} button[aria-label*='Apply to']",
                        f"{panel} button:has-text('Apply')",
                    ]

                # Global fallbacks (catches any matching button on page)
                candidate_selectors += [
                    "button[aria-label*='Easy Apply']",
                    "button:has-text('Easy Apply')",
                    ".jobs-apply-button--top-card",
                    "button.jobs-apply-button",
                    ".jobs-s-apply button",
                    "button[aria-label='Apply']",
                    "button[aria-label*='Apply now']",
                    "button[aria-label*='Apply to']",
                    "button:has-text('Apply now')",
                ]

                for sel in candidate_selectors:
                    try:
                        loc = pg.locator(sel).first
                        if loc.count() > 0:
                            loc.scroll_into_view_if_needed()
                            loc.click(force=True, timeout=4000)
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    _log(f"[{index}] Attempt {attempt + 1}: selector click failed", "warning")
                    time.sleep(2)
                    continue

                # ── Step 3: wait for modal (async render) ─────────────────────
                try:
                    pg.wait_for_selector(_MODAL_SELECTOR, timeout=7000)
                    return True
                except Exception:
                    pass

                # Modal not confirmed — maybe a dialog without Easy Apply class?
                # Check for ANY new dialog that appeared after the click.
                any_dialog = pg.query_selector("[role='dialog']")
                if any_dialog:
                    return True

                _log(f"[{index}] Attempt {attempt + 1}: click fired but modal did not appear", "warning")
                time.sleep(2)

            return False

        # ── Try to catch a new tab / popup opened by an "Apply" button ────────
        # LinkedIn's non-Easy-Apply jobs open the company's ATS in a new tab.
        # We register a popup handler BEFORE clicking the button so that if the
        # button opens a new tab instead of a modal, we capture it.
        _external_popup: list = []   # mutable container for the popup page

        def _on_popup(popup_page) -> None:
            _external_popup.append(popup_page)

        page.context.on("page", _on_popup)

        modal_opened = _find_and_click_easy_apply(page)

        # Give Playwright up to 2 s to receive the popup event
        deadline = time.time() + 2
        while not _external_popup and time.time() < deadline:
            time.sleep(0.2)

        page.context.remove_listener("page", _on_popup)

        # ── Path A: Easy Apply modal appeared ────────────────────────────────
        if modal_opened:
            _log(f"[{index}] Easy Apply modal opened — filling form...", "info")
            _screenshot(page)

            result = handle_easy_apply_modal(
                page, profile,
                job_title=title,
                job_description=description,
            )
            _screenshot(page)

            status = "applied" if result == "applied" else "skipped"
            r      = reason if result == "applied" else "Modal navigation failed"
            _send_company(index, title, company, job.get("location", ""),
                          status, r, description, job_url)
            return result

        # ── Path B: External ATS tab opened ──────────────────────────────────
        if _external_popup:
            ext_page = _external_popup[0]
            try:
                ext_page.wait_for_load_state("domcontentloaded", timeout=20_000)
            except Exception:
                pass

            ext_url = ext_page.url
            _log(f"[{index}] External ATS detected → {ext_url}", "info")
            _screenshot(ext_page)

            ext_result = _ext.apply_external(ext_page, ext_url, profile)

            try:
                ext_page.close()
            except Exception:
                pass

            status = "applied" if ext_result == "applied" else "skipped"
            r = reason if ext_result == "applied" else f"External ATS: {ext_result}"
            _send_company(index, title, company, job.get("location", ""),
                          status, r, description, ext_url)
            return ext_result

        # ── Path C: Neither modal nor popup ──────────────────────────────────
        # If the Apply button is absent, LinkedIn most likely shows "Applied"
        # because the user already submitted an application for this job.
        # Check for that before marking as plain "skipped".
        _ALREADY_APPLIED_SELECTORS = [
            ".jobs-s-apply__application-link--applied",
            "button[aria-label*='Applied']",
            "[aria-label*='You applied']",
            ".artdeco-inline-feedback__message",
        ]
        _ALREADY_APPLIED_TEXT = [
            "you applied", "application was sent", "already applied",
            "applied on", "application submitted",
        ]
        already = False
        for sel in _ALREADY_APPLIED_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    already = True
                    break
            except Exception:
                pass
        if not already:
            try:
                body = (page.inner_text("body") or "").lower()
                already = any(t in body for t in _ALREADY_APPLIED_TEXT)
            except Exception:
                pass

        if already:
            _log(f"[{index}] {title} @ {company} — Already applied (button hidden)", "info")
            _send_company(index, title, company, job.get("location", ""),
                          "already_applied", "Already applied", description, job_url)
            return "already_applied"

        _log(f"[{index}] {title} @ {company} — Apply button not clickable, skipping", "warning")
        _send_company(index, title, company, job.get("location", ""),
                      "skipped", "Apply button not clickable", description, job_url)
        return "skipped"

    except Exception as e:
        print(f"     Error: {e}")
        return "skipped"


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def take_screenshot(page, filename):
    path = os.path.join(SCRIPT_DIR, filename)
    page.screenshot(path=path)
    print(f"Screenshot saved: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    profile = load_profile()
    print(f"Profile loaded: {profile['full_name']} | {profile['current_job_title']}")

    # Init external-apply module with shared resources (standalone mode)
    _ext._init(_openai_client, _track_usage, None)

    with sync_playwright() as p:
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        context = p.chromium.launch_persistent_context(
            BROWSER_PROFILE_DIR,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            login_linkedin(page)
            take_screenshot(page, "linkedin_after_login.png")

            job_cards = get_easy_apply_jobs(page, needed=MAX_APPLICATIONS)

            results = {"applied": [], "skipped": [], "already_applied": []}

            for i, job in enumerate(job_cards[:MAX_APPLICATIONS], start=1):
                status = apply_to_job(page, job, i, profile)
                results[status].append(i)
                time.sleep(2)

            print("\n" + "=" * 50)
            print("DONE!")
            print(f"  Applied        : {len(results['applied'])}")
            print(f"  Already applied: {len(results['already_applied'])}")
            print(f"  Skipped        : {len(results['skipped'])}")
            print("=" * 50)

            log_path = os.path.join(SCRIPT_DIR, "linkedin_log.json")
            with open(log_path, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Log saved to {log_path}")

        except Exception as e:
            print(f"Error: {e}")
            take_screenshot(page, "linkedin_error.png")

        finally:
            input("\nPress Enter to close the browser...")
            context.close()


# ---------------------------------------------------------------------------
# Programmatic entry point  (called by server.py)
# ---------------------------------------------------------------------------

def run_automation(profile: dict, logger=None) -> None:
    """
    Run the full LinkedIn automation pipeline.
    Called by server.py's background thread.
    `logger` is a SessionLogger instance that streams events over WebSocket.
    """
    global _logger
    _logger = logger
    _reset_usage()   # start fresh token counters for this run

    # Inject shared resources into the external-apply module
    _ext._init(_openai_client, _track_usage, logger)

    applied_count = 0

    with sync_playwright() as p:
        # Profile folder is keyed by email — each account gets its own session.
        # Switching credentials in the UI automatically uses a different folder,
        # so the old session is never touched.
        import hashlib
        _email_slug = hashlib.md5((LINKEDIN_EMAIL or "").strip().lower().encode()).hexdigest()[:12]
        _profile_dir = os.path.join(SCRIPT_DIR, f"linkedin_browser_profile_{_email_slug}")
        os.makedirs(_profile_dir, exist_ok=True)

        context = p.chromium.launch_persistent_context(
            _profile_dir,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--window-size=1366,768",
            ],
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Start CDP screencast immediately after the page is created so that
        # every subsequent navigation and interaction is streamed live.
        # If CDP is unavailable the screencaster degrades silently; the manual
        # _screenshot() calls inside apply_to_job() act as a safety net.
        screencaster = CDPScreencaster(page, logger)
        screencaster.start()

        try:
            _log("Opening LinkedIn browser...", "info")
            login_status = login_linkedin(page)

            if login_status == "wrong_credentials":
                # Error already logged inside login_linkedin — abort cleanly.
                _log("Automation stopped: fix your LinkedIn credentials and try again.", "error")
                if logger:
                    logger.done()
                return

            if login_status == "checkpoint":
                # Security check: in server mode we can't complete it — abort.
                _log(
                    "Automation stopped: LinkedIn requires a security check "
                    "(CAPTCHA or 2FA). Please log in manually once to clear it, "
                    "then restart.",
                    "error",
                )
                if logger:
                    logger.done()
                return

            if login_status == "failed":
                _log("Automation stopped: LinkedIn login page could not be loaded.", "error")
                if logger:
                    logger.done()
                return

            _log("Logged in — searching for jobs...", "info")

            jobs = get_easy_apply_jobs(page, needed=MAX_APPLICATIONS)
            _log(f"Found {len(jobs)} Easy Apply jobs (target: {MAX_APPLICATIONS})", "found")

            for i, job in enumerate(jobs[:MAX_APPLICATIONS], start=1):
                # ── Page recovery ─────────────────────────────────────────────
                # LinkedIn's anti-bot detection or a popup/redirect during a
                # previous application can silently close the page object.
                # Detect this before each job and open a fresh page so the run
                # continues rather than crashing with "Target page... closed".
                if page.is_closed():
                    _log("Browser page closed unexpectedly — opening a fresh page.", "warning")
                    try:
                        page = context.new_page()
                        screencaster.stop()
                        screencaster = CDPScreencaster(page, logger)
                        screencaster.start()
                        # Re-authenticate: persistent context keeps cookies but
                        # a fresh page still needs to navigate to the feed.
                        relogin_status = login_linkedin(page)
                        if relogin_status == "wrong_credentials":
                            _log("Re-login failed — wrong credentials. Stopping automation.", "error")
                            break
                    except Exception as recovery_exc:
                        _log(f"Page recovery failed: {recovery_exc}", "error")
                        break   # browser context is dead — abort the run

                status = apply_to_job(page, job, i, profile)

                if status == "applied":
                    applied_count += 1
                    if logger:
                        logger.progress(applied_count, MAX_APPLICATIONS)
                # Random delay between jobs — reduces automation detection risk
                time.sleep(random.uniform(2.0, 4.5))

            summary = f"Done! {applied_count}/{MAX_APPLICATIONS} applications submitted."
            _log(summary, "success")

            # Send cost summary to the frontend
            cost = _cost_summary()
            _log(
                f"GPT cost: ${cost['cost_usd']:.4f} "
                f"({cost['total_tokens']:,} tokens — "
                f"{cost['input_tokens']:,} in / {cost['output_tokens']:,} out)",
                "info",
            )
            if logger:
                logger.cost(cost)   # dedicated cost frame
                logger.done(summary)

        except Exception as exc:
            _log(f"Fatal error: {exc}", "error")
            if logger:
                logger.fail(str(exc))

        finally:
            # Stop the CDP screencast before closing the browser so Chrome
            # can process the Page.stopScreencast command cleanly.
            screencaster.stop()
            context.close()
            _logger = None


if __name__ == "__main__":
    main()