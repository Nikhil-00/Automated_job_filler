"""
email_otp.py
------------
Connects to Gmail via IMAP and extracts OTP codes from incoming emails.
Used by the job application script to handle email verification during
auto-registration on job portals.
"""

import imaplib
import email
import re
import time
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_ADDRESS     = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT   = 993


def _connect():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    return mail


def _extract_otp(text: str) -> str | None:
    """Extract a numeric OTP (4-8 digits) from email body text."""
    # Common OTP patterns
    patterns = [
        r'\b(\d{6})\b',   # 6-digit (most common)
        r'\b(\d{4})\b',   # 4-digit
        r'\b(\d{8})\b',   # 8-digit
        r'OTP[:\s]+(\d+)',
        r'code[:\s]+(\d+)',
        r'verification[:\s]+(\d+)',
        r'PIN[:\s]+(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _get_email_body(msg) -> str:
    """Extract plain text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    body += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except:
                    pass
            elif content_type == "text/html" and not body:
                try:
                    html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    # Strip HTML tags
                    body += re.sub(r'<[^>]+>', ' ', html)
                except:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except:
            pass
    return body


def wait_for_otp(sender_filter: str = None, timeout: int = 60, poll_interval: int = 5) -> str | None:
    """
    Poll Gmail inbox for a new OTP email and return the OTP code.

    Args:
        sender_filter: Optional email domain or address to filter by (e.g. 'oracle.com')
        timeout:       Max seconds to wait (default 60)
        poll_interval: Seconds between checks (default 5)

    Returns:
        OTP string if found, None if timed out
    """
    print(f"     Waiting for OTP email (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        try:
            mail = _connect()
            mail.select("inbox")

            # Search for unseen emails
            if sender_filter:
                _, data = mail.search(None, f'(UNSEEN FROM "{sender_filter}")')
            else:
                _, data = mail.search(None, "UNSEEN")

            ids = data[0].split()
            if ids:
                # Check most recent emails first
                for email_id in reversed(ids[-5:]):
                    _, msg_data = mail.fetch(email_id, "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])

                    subject = msg.get("Subject", "")
                    body    = _get_email_body(msg)
                    full_text = subject + " " + body

                    otp = _extract_otp(full_text)
                    if otp:
                        print(f"     OTP found: {otp} (from subject: {subject[:50]})")
                        mail.logout()
                        return otp

            mail.logout()

        except Exception as e:
            print(f"     Gmail check error: {e}")

        time.sleep(poll_interval)

    print("     Timed out waiting for OTP.")
    return None


def test_connection():
    """Test that Gmail IMAP connection works."""
    try:
        mail = _connect()
        mail.select("inbox")
        print(f"Connected to Gmail as {GMAIL_ADDRESS}")
        mail.logout()
        return True
    except Exception as e:
        print(f"Gmail connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
