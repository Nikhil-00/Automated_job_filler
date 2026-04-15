from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from .email_otp import wait_for_otp
import time
import json
import os

load_dotenv()

# Directory where this script lives
SCRIPT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# =============================================
# CONFIG
# =============================================
NAUKRI_EMAIL     = "nikhilpandey4000@gmail.com"
NAUKRI_PASSWORD  = "0..@Pandey"
JOB_SEARCH_QUERY = "Data Scientist"
JOB_LOCATION     = "India"
MAX_APPLICATIONS = 20

PORTAL_EMAIL    = os.getenv("GMAIL_ADDRESS", NAUKRI_EMAIL)
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD", "0..@Pandey07")
# =============================================


def load_profile() -> dict:
    path = os.path.join(SCRIPT_DIR, "profile.json")
    if not os.path.exists(path):
        raise FileNotFoundError("profile.json not found. Run parse_resume.py first.")
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

def detect_ats(url: str) -> str:
    u = url.lower()
    if "greenhouse.io" in u or "boards.greenhouse" in u:
        return "greenhouse"
    if "lever.co" in u:
        return "lever"
    if "workday.com" in u or "myworkdayjobs.com" in u:
        return "workday"
    if "smartrecruiters.com" in u:
        return "smartrecruiters"
    if "zohorecruit.com" in u or "zoho.com/recruit" in u:
        return "zoho"
    if "taleo.net" in u:
        return "taleo"
    if "bamboohr.com" in u:
        return "bamboohr"
    if "icims.com" in u:
        return "icims"
    if "keka.com" in u or "kekahr.com" in u:
        return "keka"
    if "darwinbox.com" in u:
        return "darwinbox"
    if "freshteam.com" in u:
        return "freshteam"
    if "oraclecloud.com" in u or "taleo.net" in u or "oracle.com/careers" in u:
        return "oracle"
    if "apprenticeshipindia.gov.in" in u or "nats.edu.in" in u:
        return "skillindia"
    if "hire.trakstar.com" in u:
        return "trakstar"
    if "career." in u and "jobs" in u:
        return "unknown"
    return "unknown"


# ---------------------------------------------------------------------------
# Page guards — run these before attempting to fill any external form
# ---------------------------------------------------------------------------

def accept_cookies(page):
    """Click any cookie consent / GDPR accept button so it doesn't block the form."""
    cookie_selectors = [
        "button:has-text('Accept All Cookies')",
        "button:has-text('Accept all cookies')",
        "button:has-text('Accept All')",
        "button:has-text('Accept Cookies')",
        "button:has-text('Accept')",
        "button:has-text('I Accept')",
        "button:has-text('Agree')",
        "button:has-text('OK')",
        "button:has-text('Got it')",
        "button:has-text('Allow all')",
        "button#onetrust-accept-btn-handler",
        "button.cookie-accept",
        "[id*='cookie'] button",
        "[class*='cookie'] button:has-text('Accept')",
        "[class*='consent'] button:has-text('Accept')",
    ]
    for sel in cookie_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(1)
                print("     Cookie popup dismissed.")
                return
        except:
            continue


def is_valid_apply_page(page, url: str) -> bool:
    """
    Returns False if we landed on the wrong page:
    - A PDF file
    - A job search / listing page (not a specific job apply form)
    - A company careers homepage
    """
    u = url.lower()

    # PDF — browser renders it, no form exists
    if u.endswith(".pdf") or "application/pdf" in page.content()[:200].lower():
        print("     Page is a PDF — no form to fill, skipping.")
        return False

    # Detect search/listing pages by URL patterns
    bad_url_patterns = [
        "/search?", "/jobs?", "/careers?", "search-results",
        "/job-list", "/vacancies?",
    ]
    for pattern in bad_url_patterns:
        if pattern in u:
            print("     Landed on a job search page, not an apply form — skipping.")
            return False

    # Detect search pages by page content — multiple job cards visible
    try:
        job_list_indicators = [
            ".job-listing", ".job-card", ".jobsList",
            "[class*='search-result']", "[class*='job-list']",
        ]
        for sel in job_list_indicators:
            els = page.query_selector_all(sel)
            if len(els) > 3:
                print("     Page shows job listings, not an apply form — skipping.")
                return False
    except:
        pass

    # Detect if there's actually any form on the page
    try:
        has_form = page.query_selector(
            "form, input[type='email'], input[type='text'], input[type='file']"
        )
        if not has_form:
            print("     No application form found on this page — skipping.")
            return False
    except:
        pass

    return True


def _select_dropdown(page, selectors: list, value: str):
    """Select a value from a <select> dropdown."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.select_option(label=value)
                return True
        except:
            try:
                el = page.query_selector(sel)
                if el:
                    el.select_option(value=value)
                    return True
            except:
                continue
    return False


# ---------------------------------------------------------------------------
# ATS form fillers
# ---------------------------------------------------------------------------

def _fill(page, selectors: list, value: str):
    """Try each selector in order; fill the first one found."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(value)
                return True
        except:
            continue
    return False


def _upload(page, selectors: list, path: str):
    """
    Upload a file to a file input.
    Handles both visible and hidden inputs (most ATS sites hide the <input type='file'>
    behind a styled button). Falls back to uploading on any file input found on the page.
    """
    # 1. Try provided selectors first
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.set_input_files(path)
                print(f"     CV uploaded via selector: {sel}")
                return True
        except:
            continue

    # 2. Find ALL file inputs on the page (including hidden ones)
    try:
        all_file_inputs = page.query_selector_all("input[type='file']")
        for inp in all_file_inputs:
            try:
                inp.set_input_files(path)
                print("     CV uploaded via hidden file input.")
                return True
            except:
                continue
    except:
        pass

    # 3. Some sites use drag-and-drop zones — trigger file chooser via click
    try:
        for drop_sel in [
            "[class*='dropzone']", "[class*='drop-zone']",
            "[class*='upload-area']", "[class*='file-upload']",
            "label[for*='resume']", "label[for*='cv']",
            "button:has-text('Upload')", "button:has-text('Choose file')",
            "button:has-text('Browse')",
        ]:
            el = page.query_selector(drop_sel)
            if el and el.is_visible():
                with page.expect_file_chooser() as fc_info:
                    el.click()
                fc = fc_info.value
                fc.set_files(path)
                print(f"     CV uploaded via file chooser: {drop_sel}")
                return True
    except:
        pass

    print("     Warning: Could not find a CV upload field on this page.")
    return False


def _click_submit(page):
    for sel in [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Apply')",
        "button:has-text('Send application')",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                return True
        except:
            continue
    return False


def apply_greenhouse(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    _fill(page, ["#first_name", "input[name='first_name']", "input[placeholder*='First' i]"], first)
    _fill(page, ["#last_name",  "input[name='last_name']",  "input[placeholder*='Last' i]"],  last)
    _fill(page, ["#email", "input[name='email']", "input[type='email']",
                 "input[placeholder*='Email' i]"],                                             profile["email"])
    _fill(page, ["#phone", "input[name='phone']", "input[type='tel']",
                 "input[placeholder*='Phone' i]"],                                             profile["phone"])

    # Location / city
    _fill(page, [
        "input[name='location']", "input[placeholder*='Location' i]",
        "input[placeholder*='City' i]", "#location",
    ], profile.get("current_city", "Delhi, India"))

    if profile.get("linkedin_url"):
        _fill(page, [
            "#linkedin_url", "input[name='linkedin_profile']",
            "input[placeholder*='LinkedIn' i]",
        ], profile["linkedin_url"])

    # Notice period — try dropdown first, then text input
    notice = profile.get("notice_period", "30 days")
    if not _select_dropdown(page, [
        "select[name*='notice' i]", "select[id*='notice' i]",
        "select[placeholder*='notice' i]",
    ], notice):
        _fill(page, [
            "input[name*='notice' i]", "input[placeholder*='notice' i]",
            "input[placeholder*='Notice' i]",
        ], notice)

    # Greenhouse resume upload — uses an "Attach" button that opens file chooser
    # Try hidden file input first, then the "Attach" button
    uploaded = False
    try:
        all_inputs = page.query_selector_all("input[type='file']")
        for inp in all_inputs:
            try:
                inp.set_input_files(profile["resume_path"])
                print("     CV uploaded via Greenhouse file input.")
                uploaded = True
                break
            except:
                continue
    except:
        pass

    if not uploaded:
        # Click the "Attach" button and handle file chooser
        for sel in ["button:has-text('Attach')", "a:has-text('Attach')",
                    "label:has-text('Attach')", "[class*='attach']"]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        btn.click()
                    fc_info.value.set_files(profile["resume_path"])
                    print("     CV uploaded via Greenhouse Attach button.")
                    uploaded = True
                    break
            except:
                continue

    time.sleep(2)

    # Verify CV was accepted (error message gone)
    try:
        err = page.query_selector("text=Resume/CV is required")
        if err and err.is_visible():
            print("     Warning: CV still showing as required after upload attempt.")
    except:
        pass

    return _click_submit(page)


def apply_lever(page, profile: dict) -> bool:
    time.sleep(2)
    _fill(page, ["input[name='name']",  "#name",  "input[placeholder*='name' i]"],    profile["full_name"])
    _fill(page, ["input[name='email']", "#email", "input[type='email']"],              profile["email"])
    _fill(page, ["input[name='phone']", "#phone", "input[type='tel']"],                profile["phone"])
    _fill(page, ["input[name='org']",   "input[placeholder*='company' i]",
                 "input[placeholder*='organization' i]"],                              profile.get("current_company", ""))

    if profile.get("linkedin_url"):
        _fill(page, [
            "input[name='urls[LinkedIn]']",
            "input[placeholder*='LinkedIn' i]",
        ], profile["linkedin_url"])

    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def apply_workday(page, profile: dict) -> bool:
    """Workday is multi-step — fill what we can on the first screen."""
    time.sleep(3)
    name_parts = profile["full_name"].split(" ", 1)

    _fill(page, ["input[data-automation-id='legalNameSection_firstName']",
                 "input[placeholder*='First' i]"], name_parts[0])
    _fill(page, ["input[data-automation-id='legalNameSection_lastName']",
                 "input[placeholder*='Last' i]"],  name_parts[1] if len(name_parts) > 1 else "")
    _fill(page, ["input[data-automation-id='email']",  "input[type='email']"], profile["email"])
    _fill(page, ["input[data-automation-id='phone']",  "input[type='tel']"],   profile["phone"])

    _upload(page, ["input[type='file']",
                   "input[data-automation-id='file-upload-input-ref']"], profile["resume_path"])
    time.sleep(1)

    # Workday "Next" button (multi-step)
    for sel in ["button[data-automation-id='bottom-navigation-next-button']",
                "button:has-text('Next')", "button:has-text('Apply')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                return True
        except:
            continue
    return False


def apply_smartrecruiters(page, profile: dict) -> bool:
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    # SR shows a job detail page first — click their Apply button to open the form
    for sel in ["button[data-ui='apply-btn']", "a[data-ui='apply-btn']",
                "button:has-text('Apply')", "a:has-text('Apply now')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                break
        except:
            continue

    # Wait for the application form/modal to appear
    try:
        page.wait_for_selector("input[name='firstName'], input[type='email']", timeout=8000)
    except:
        time.sleep(3)

    # Step 1 — personal info
    _fill(page, ["input[name='firstName']",   "input[placeholder*='First' i]"],   first)
    _fill(page, ["input[name='lastName']",    "input[placeholder*='Last' i]"],    last)
    _fill(page, ["input[name='email']",       "input[type='email']"],             profile["email"])
    _fill(page, ["input[name='phoneNumber']", "input[type='tel']",
                 "input[placeholder*='Phone' i]"],                                profile["phone"])

    # Resume upload
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)

    # Click through each step (Next → Next → Submit)
    for step in range(4):
        clicked = False
        for sel in [
            "button[data-ui='submit-btn']",
            "button[data-ui='next-btn']",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button[type='submit']",
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    time.sleep(2)
                    clicked = True
                    break
            except:
                continue

        # Check if we reached a success page
        for success_sel in ["text=Application submitted", "text=Thank you",
                            "text=Successfully applied", "[class*='success']"]:
            try:
                if page.query_selector(success_sel):
                    return True
            except:
                continue

        if not clicked:
            break

    return True  # assume applied if we got through the steps


def apply_zoho(page, profile: dict) -> bool:
    """Zoho Recruit career pages."""
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    # Zoho may have an "Apply" button on the job page
    for sel in ["a:has-text('Apply')", "button:has-text('Apply')",
                "a:has-text('Apply for this job')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except:
            continue

    # Wait for form
    try:
        page.wait_for_selector("input[name='firstName'], input[type='email'], "
                               "input[placeholder*='name' i]", timeout=6000)
    except:
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
    """Keka HR career portal (popular in Indian companies)."""
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
    """Darwinbox ATS (used by many large Indian companies)."""
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


def apply_generic(page, profile: dict) -> bool:
    """
    Best-effort filler for custom company career pages with no known ATS.
    Tries common field patterns and submits.
    """
    time.sleep(2)
    name_parts = profile["full_name"].split(" ", 1)
    first = name_parts[0]
    last  = name_parts[1] if len(name_parts) > 1 else ""

    # Always try separate first/last fields first to avoid dumping full name in First Name
    filled_first = _fill(page, [
        "input[name='first_name']", "input[name='firstName']",
        "input[placeholder='First Name']", "input[placeholder='First name']",
        "input[id*='first' i]",
    ], first)
    filled_last = _fill(page, [
        "input[name='last_name']", "input[name='lastName']",
        "input[placeholder='Last Name']", "input[placeholder='Last name']",
        "input[id*='last' i]",
    ], last)

    # Only fall back to a single full-name field if no first/last fields found
    if not filled_first and not filled_last:
        _fill(page, [
            "input[name='name']",
            "input[placeholder='Full Name']", "input[placeholder='Full name']",
            "input[placeholder*='Your name' i]",
        ], profile["full_name"])

    _fill(page, [
        "input[type='email']", "input[name='email']",
        "input[id*='email' i]", "input[placeholder*='email' i]",
    ], profile["email"])

    _fill(page, [
        "input[type='tel']",
        "input[name='phone']", "input[name='mobile']", "input[name='phoneNumber']",
        "input[id*='phone' i]", "input[id*='mobile' i]",
        "input[placeholder*='phone' i]", "input[placeholder*='mobile' i]",
        "input[placeholder*='number' i]",
    ], profile["phone"])

    if profile.get("linkedin_url"):
        _fill(page, [
            "input[placeholder*='linkedin' i]", "input[name*='linkedin' i]",
            "input[id*='linkedin' i]",
        ], profile["linkedin_url"])

    # Fill "About yourself" / cover letter textarea with a short bio
    bio = (
        f"I am {profile['full_name']}, currently working as {profile.get('current_job_title', 'a Data Scientist')} "
        f"at {profile.get('current_company', '')} with {profile.get('years_of_experience', '1')} years of experience "
        f"in Data Science and Machine Learning. Notice period: {profile.get('notice_period', '30 days')}."
    )
    for sel in [
        "textarea[name*='about' i]", "textarea[name*='cover' i]",
        "textarea[placeholder*='about' i]", "textarea[placeholder*='yourself' i]",
        "textarea[placeholder*='cover' i]", "textarea[placeholder*='message' i]",
        "textarea",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(bio)
                break
        except:
            continue

    # Resume upload
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)

    # Try to submit
    submitted = False
    for sel in [
        "button[type='submit']", "input[type='submit']",
        "button:has-text('Submit')", "button:has-text('Apply')",
        "button:has-text('Send')", "button:has-text('Apply now')",
        "a:has-text('Submit')", "a:has-text('Apply now')",
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click()
                time.sleep(3)
                submitted = True
                break
        except:
            continue
    return submitted


def apply_bamboohr(page, profile: dict) -> bool:
    time.sleep(2)
    _fill(page, ["#first_name", "input[name='first_name']"], profile["full_name"].split()[0])
    _fill(page, ["#last_name",  "input[name='last_name']"],  " ".join(profile["full_name"].split()[1:]))
    _fill(page, ["#email",      "input[name='email']",  "input[type='email']"], profile["email"])
    _fill(page, ["#phone",      "input[name='phone']",  "input[type='tel']"],   profile["phone"])
    _upload(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    return _click_submit(page)


def _handle_login_or_register(page, email: str, password: str,
                               email_selectors: list, pass_selectors: list,
                               submit_sel: str, otp_sender: str = None):
    """
    Generic helper: tries to log in first; if no account exists, registers.
    Handles OTP automatically via Gmail.
    """
    # Fill email
    _fill(page, email_selectors, email)
    time.sleep(1)

    # Click Next/Continue if it's a two-step login (email first, then password)
    for sel in ["button:has-text('Next')", "button:has-text('Continue')",
                "button[type='submit']", "input[type='submit']"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except:
            continue

    # Fill password if field appeared
    _fill(page, pass_selectors, password)
    time.sleep(1)

    # Submit login
    for sel in [submit_sel, "button[type='submit']", "input[type='submit']",
                "button:has-text('Sign in')", "button:has-text('Login')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(3)
                break
        except:
            continue

    # Handle OTP / email verification if it appears
    for otp_field_sel in ["input[placeholder*='OTP' i]", "input[placeholder*='code' i]",
                           "input[placeholder*='verification' i]", "input[name*='otp' i]",
                           "input[maxlength='6']", "input[maxlength='4']"]:
        try:
            otp_field = page.wait_for_selector(otp_field_sel, timeout=5000)
            if otp_field and otp_field.is_visible():
                otp = wait_for_otp(sender_filter=otp_sender, timeout=60)
                if otp:
                    otp_field.fill(otp)
                    time.sleep(1)
                    _click_submit(page)
                    time.sleep(3)
                break
        except:
            continue


def apply_oracle(page, profile: dict) -> bool:
    """
    Oracle HCM / Fusion (used by EXL, many large companies).
    Auto-registers or logs in, then applies.
    """
    time.sleep(2)
    current_url = page.url

    # Oracle HCM asks for email first on a "Let's get started" screen
    _fill(page, [
        "input[type='email']",
        "input[placeholder*='email' i]",
        "input[name*='email' i]",
    ], PORTAL_EMAIL)
    time.sleep(1)

    # Click the arrow / Next button
    for sel in ["button[type='submit']", "input[type='submit']",
                "button:has-text('Next')", "button.next", "button[aria-label='Next']",
                "svg[aria-label='Next']", "button:has-text('>')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(3)
                break
        except:
            continue

    # Check if password field appeared (existing account) or registration form
    password_appeared = False
    for sel in ["input[type='password']", "input[name*='password' i]"]:
        try:
            el = page.wait_for_selector(sel, timeout=5000)
            if el and el.is_visible():
                password_appeared = True
                _fill(page, [sel], PORTAL_PASSWORD)
                break
        except:
            continue

    if not password_appeared:
        # Registration flow — fill new account details
        name_parts = profile["full_name"].split(" ", 1)
        _fill(page, ["input[name*='firstName' i]", "input[placeholder*='First' i]"], name_parts[0])
        _fill(page, ["input[name*='lastName' i]",  "input[placeholder*='Last' i]"],
              name_parts[1] if len(name_parts) > 1 else "")
        _fill(page, ["input[type='password']", "input[name*='password' i]"], PORTAL_PASSWORD)
        _fill(page, ["input[name*='confirm' i]", "input[placeholder*='confirm' i]"], PORTAL_PASSWORD)

    # Submit login/registration
    _click_submit(page)
    time.sleep(3)

    # Handle OTP if sent to email
    for otp_sel in ["input[maxlength='6']", "input[placeholder*='code' i]",
                    "input[placeholder*='OTP' i]", "input[name*='otp' i]"]:
        try:
            el = page.wait_for_selector(otp_sel, timeout=6000)
            if el and el.is_visible():
                print("     OTP required — checking Gmail...")
                otp = wait_for_otp(sender_filter="oracle.com", timeout=60)
                if otp:
                    el.fill(otp)
                    _click_submit(page)
                    time.sleep(3)
                break
        except:
            continue

    # Now on the application form — fill it
    _fill(page, ["input[type='file']"], profile["resume_path"])
    time.sleep(1)
    _upload(page, ["input[type='file']"], profile["resume_path"])

    # Click through Oracle's multi-step apply flow
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
            except:
                continue

        # Check for success
        for success_sel in ["text=Application submitted", "text=Thank you for applying",
                            "text=Successfully submitted"]:
            try:
                if page.query_selector(success_sel):
                    return True
            except:
                continue

    return True


def apply_skillindia(page, profile: dict) -> bool:
    """
    Skill India / Apprenticeship India portal.
    Auto-registers if no account, then applies.
    """
    time.sleep(2)

    # Click Login/Register button
    for sel in ["a:has-text('Login')", "button:has-text('Login')",
                "a:has-text('Login/Register')", "button:has-text('Login/Register')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except:
            continue

    # Check if on login page — try to log in first
    email_filled = _fill(page, [
        "input[type='email']", "input[name='email']",
        "input[placeholder*='email' i]", "input[id*='email' i]",
    ], PORTAL_EMAIL)

    if email_filled:
        _fill(page, ["input[type='password']", "input[name='password']"], PORTAL_PASSWORD)
        _click_submit(page)
        time.sleep(3)

        # Check if login failed (still on login page) → register instead
        if "login" in page.url.lower() or "signin" in page.url.lower():
            # Look for Register link
            for sel in ["a:has-text('Register')", "a:has-text('Sign up')",
                        "button:has-text('Register')"]:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(2)
                        break
                except:
                    continue

            # Fill registration form
            name_parts = profile["full_name"].split(" ", 1)
            _fill(page, ["input[name='firstName']", "input[placeholder*='First' i]"], name_parts[0])
            _fill(page, ["input[name='lastName']",  "input[placeholder*='Last' i]"],
                  name_parts[1] if len(name_parts) > 1 else "")
            _fill(page, ["input[type='email']", "input[name='email']"], PORTAL_EMAIL)
            _fill(page, ["input[type='password']", "input[name='password']"], PORTAL_PASSWORD)
            _fill(page, ["input[name='phone']", "input[type='tel']"], profile["phone"])
            _click_submit(page)
            time.sleep(3)

            # Handle OTP from email
            for otp_sel in ["input[maxlength='6']", "input[placeholder*='OTP' i]",
                            "input[placeholder*='code' i]"]:
                try:
                    el = page.wait_for_selector(otp_sel, timeout=8000)
                    if el and el.is_visible():
                        print("     OTP required — checking Gmail...")
                        otp = wait_for_otp(sender_filter="apprenticeshipindia.gov.in", timeout=60)
                        if otp:
                            el.fill(otp)
                            _click_submit(page)
                            time.sleep(3)
                    break
                except:
                    continue

    # Now apply for the opportunity
    for sel in ["button:has-text('Apply for This Opportunity')",
                "a:has-text('Apply for This Opportunity')",
                "button:has-text('Apply')"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(2)
                return True
        except:
            continue

    return False


def apply_trakstar(page, profile: dict) -> bool:
    """Trakstar Hire ATS (e.g. Wadhwani AI)."""
    time.sleep(2)

    # Click the Apply button to open the application form
    for sel in ["button:has-text('Apply')", "a:has-text('Apply')",
                "input[value='Apply']"]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible() and "indeed" not in btn.inner_text().lower():
                btn.click()
                time.sleep(2)
                break
        except:
            continue

    # Wait for form to load
    try:
        page.wait_for_selector("input[type='text'], input[type='email']", timeout=6000)
    except:
        time.sleep(2)

    name_parts = profile["full_name"].split(" ", 1)
    _fill(page, ["input[name='first_name']", "input[placeholder='First Name']",
                 "input[placeholder*='First' i]"], name_parts[0])
    _fill(page, ["input[name='last_name']",  "input[placeholder='Last Name']",
                 "input[placeholder*='Last' i]"],
          name_parts[1] if len(name_parts) > 1 else "")
    _fill(page, ["input[type='email']", "input[name='email']",
                 "input[placeholder*='email' i]"], profile["email"])
    _fill(page, ["input[type='tel']", "input[name='phone']",
                 "input[placeholder*='phone' i]"], profile["phone"])

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


# ---------------------------------------------------------------------------
# External apply orchestrator
# ---------------------------------------------------------------------------

def apply_external(job_page, context, profile: dict) -> str:
    """
    Find the external apply button on the Naukri job page,
    open the company site in a new tab, detect the ATS, and fill the form.
    """
    external_btn = None
    for sel in [
        "a:has-text('Apply on Company Site')",
        "a:has-text('Apply on company website')",
        "button:has-text('Apply on Company Site')",
        "[class*='apply']:has-text('Apply')",
        "a[target='_blank']:has-text('Apply')",
    ]:
        try:
            el = job_page.query_selector(sel)
            if el and el.is_visible():
                external_btn = el
                break
        except:
            continue

    if not external_btn:
        print("     Could not find external apply button — skipping.")
        return "skipped"

    # Capture the new tab that opens when clicking the external link
    with context.expect_page() as new_page_info:
        external_btn.click()
    ext_page = new_page_info.value
    ext_page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    # Step 1 — dismiss cookie popup before anything else
    accept_cookies(ext_page)

    # Step 2 — check we actually landed on an apply form
    if not is_valid_apply_page(ext_page, ext_page.url):
        ext_page.close()
        return "skipped"

    ats = detect_ats(ext_page.url)
    print(f"     Detected ATS: {ats} ({ext_page.url[:60]}...)")

    handler = ATS_HANDLERS.get(ats, apply_generic)

    try:
        success = handler(ext_page, profile)

        # Take a screenshot so the user can verify what happened
        screenshot_path = os.path.join(SCRIPT_DIR, f"external_apply_{ats}_{int(time.time())}.png")
        try:
            ext_page.screenshot(path=screenshot_path)
            print(f"     Screenshot saved: {screenshot_path}")
        except:
            pass

        ext_page.close()

        if success:
            # Double-check: if we're still on a form page with errors, it didn't work
            error_indicators = [
                "text=This field is required",
                "text=Please fill out this field",
                "text=required field",
                "[class*='error']:visible",
                "[class*='invalid']:visible",
            ]
            has_errors = False
            for err_sel in error_indicators:
                try:
                    if ext_page.query_selector(err_sel):
                        has_errors = True
                        break
                except:
                    continue

            if has_errors:
                print("     Form submitted but validation errors remain — skipping.")
                return "skipped"

            print("     Applied on external site!")
            return "applied"
        else:
            print("     Could not submit form — skipping.")
            return "skipped"
    except Exception as e:
        print(f"     External apply error: {e}")
        try:
            ext_page.close()
        except:
            pass
        return "skipped"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_naukri(page):
    print("Opening Naukri...")
    page.goto("https://www.naukri.com", wait_until="networkidle")
    time.sleep(2)

    print("Clicking Login...")
    for sel in [
        "a[title='Jobseeker Login']",
        "a[href*='login']",
        "[data-ga-track*='login' i]",
        "text=Login",
        "text=Log in",
    ]:
        try:
            page.click(sel, timeout=5000)
            break
        except:
            continue

    time.sleep(2)
    print("Entering credentials...")
    page.fill("input[placeholder='Enter your active Email ID / Username']", NAUKRI_EMAIL)
    page.fill("input[placeholder='Enter your password']", NAUKRI_PASSWORD)
    page.click("button[type='submit']")
    time.sleep(4)

    if "naukri.com" in page.url:
        print("Login successful!")
    else:
        raise Exception("Login failed. Check your credentials.")


# ---------------------------------------------------------------------------
# Job link scraper
# ---------------------------------------------------------------------------

def get_job_links(page) -> list:
    print(f"\nSearching for '{JOB_SEARCH_QUERY}' jobs in {JOB_LOCATION}...")
    search_url = (
        f"https://www.naukri.com/{JOB_SEARCH_QUERY.lower().replace(' ', '-')}-jobs"
        f"?k={JOB_SEARCH_QUERY.replace(' ', '%20')}&l={JOB_LOCATION}"
    )
    page.goto(search_url, wait_until="domcontentloaded")
    time.sleep(3)

    links = []
    for sel in [
        "article.jobTuple a.title",
        ".cust-job-tuple a.title",
        ".jobTitle a",
        "a.job-title",
    ]:
        elements = page.query_selector_all(sel)
        if elements:
            for el in elements:
                href = el.get_attribute("href")
                if href and "naukri.com" in href:
                    links.append(href)
            break

    seen, unique = set(), []
    for l in links:
        if l not in seen:
            seen.add(l)
            unique.append(l)

    print(f"Found {len(unique)} job listings on page.")
    return unique


# ---------------------------------------------------------------------------
# Per-job apply logic
# ---------------------------------------------------------------------------

def try_apply_to_job(page, context, job_url: str, index: int, profile: dict) -> str:
    job_page = context.new_page()
    try:
        job_page.goto(job_url, wait_until="domcontentloaded")
        time.sleep(2)

        # Extract title & company
        title, company = "Unknown", "Unknown"
        for sel in ["h1.jd-header-title", ".jd-header-title", "h1[class*='title']", "h1"]:
            try:
                el = job_page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if t:
                        title = t
                        break
            except: continue

        for sel in [".jd-header-comp-name a", ".jd-header-comp-name",
                    "[class*='comp-name'] a", "[class*='comp-name']",
                    "[class*='companyName']", "[class*='company-name']"]:
            try:
                el = job_page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if t:
                        company = t
                        break
            except: continue

        print(f"\n[{index}] {title} @ {company}")

        # Already applied?
        for indicator in ["text=Applied", "text=You have already applied"]:
            try:
                el = job_page.query_selector(indicator)
                if el and el.is_visible():
                    print("     Already applied — skipping.")
                    return "already_applied"
            except: continue

        # Look for Naukri Easy Apply button
        easy_apply_btn = None
        for sel in ["button.apply-button", "button[class*='ia-apply']",
                    "button[class*='easy-apply']", "button[id*='apply']"]:
            try:
                btn = job_page.query_selector(sel)
                if btn and btn.is_visible():
                    easy_apply_btn = btn
                    break
            except: continue

        # Fallback: plain "Apply" button (not "Apply on Company Site")
        if not easy_apply_btn:
            try:
                for btn in job_page.query_selector_all("button"):
                    if btn.inner_text().strip().lower() == "apply" and btn.is_visible():
                        easy_apply_btn = btn
                        break
            except: pass

        if easy_apply_btn:
            # --- Naukri Easy Apply ---
            easy_apply_btn.click()
            time.sleep(2)
            for sel in ["button:has-text('Apply')", "button:has-text('Confirm')",
                        "button:has-text('Submit')", "button:has-text('Done')"]:
                try:
                    btn = job_page.wait_for_selector(sel, timeout=3000)
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(1)
                        break
                except: continue

            time.sleep(2)
            for indicator in ["text=Successfully Applied", "text=Application Submitted",
                              "text=You have applied", "text=Applied successfully"]:
                try:
                    job_page.wait_for_selector(indicator, timeout=3000)
                    print("     Applied successfully! (Easy Apply)")
                    return "applied"
                except: continue

            print("     Easy Apply clicked (could not confirm — check manually).")
            return "applied"

        else:
            # --- External Apply ---
            print("     External apply detected — trying to apply on company site...")
            return apply_external(job_page, context, profile)

    except Exception as e:
        print(f"     Error: {e}")
        return "skipped"
    finally:
        try:
            job_page.close()
        except:
            pass


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def take_screenshot(page, filename):
    path = os.path.join(SCRIPT_DIR, filename)
    page.screenshot(path=path, full_page=False)
    print(f"Screenshot saved: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    profile = load_profile()
    print(f"Profile loaded: {profile['full_name']} | {profile['current_job_title']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            login_naukri(page)
            take_screenshot(page, "after_login.png")

            job_links = get_job_links(page)
            results = {"applied": [], "skipped": [], "already_applied": []}

            for i, link in enumerate(job_links[:MAX_APPLICATIONS], start=1):
                status = try_apply_to_job(page, context, link, i, profile)
                results[status].append(link)
                time.sleep(1)

            print("\n" + "=" * 50)
            print("DONE!")
            print(f"  Applied        : {len(results['applied'])}")
            print(f"  Already applied: {len(results['already_applied'])}")
            print(f"  Skipped        : {len(results['skipped'])}")
            print("=" * 50)

            log_path = os.path.join(SCRIPT_DIR, "applications_log.json")
            with open(log_path, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Log saved to {log_path}")

        except Exception as e:
            print(f"Error: {e}")
            take_screenshot(page, "error_screenshot.png")

        finally:
            input("\nPress Enter to close the browser...")
            browser.close()


if __name__ == "__main__":
    main()
