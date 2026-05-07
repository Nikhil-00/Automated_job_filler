"""
backend/services/email_service.py
──────────────────────────────────
Production-grade email service using Resend API.
"""
import logging
import requests
from typing import Optional

from backend.config import RESEND_API_KEY, EMAIL_FROM

logger = logging.getLogger(__name__)

class EmailService:
    @staticmethod
    def send_email(to_email: str, subject: str, html_content: str) -> bool:
        """
        Sends an email using Resend API.
        Returns True if successful, False otherwise.
        """
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }

        logger.info(f"Attempting to send email to {to_email} via Resend API")
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code in [200, 201]:
                logger.info(f"Email sent successfully to {to_email}. ID: {response.json().get('id')}")
                return True
            else:
                error_data = response.json()
                logger.error(f"Resend API error ({response.status_code}): {error_data}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error while calling Resend API: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in EmailService: {str(e)}")
            return False

def send_otp_email_v2(to_email: str, name: str, otp: str) -> None:
    """
    Styled HTML OTP email using Resend Service.
    This replaces the old SMTP-based send_otp_email.
    """
    subject = f"{otp} is your AutoApply AI verification code"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            .container {{
                background-color: #0f0f1a;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 40px 16px;
                color: #e2e8f0;
            }}
            .card {{
                max-width: 480px;
                margin: 0 auto;
                background-color: #1a1a2e;
                border-radius: 16px;
                border: 1px solid #2d2d4e;
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #7c3aed, #2563eb);
                padding: 24px 32px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            .content {{
                padding: 32px;
            }}
            .otp-box {{
                background: #0f0f1a;
                border: 2px solid #7c3aed;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                margin: 24px 0;
            }}
            .otp-code {{
                font-size: 40px;
                font-weight: 800;
                letter-spacing: 12px;
                color: #a78bfa;
                font-family: monospace;
            }}
            .footer {{
                margin-top: 24px;
                color: #64748b;
                font-size: 12px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="header">
                    <h1>AutoApply AI</h1>
                    <p style="margin:4px 0 0;color:rgba(255,255,255,.75);font-size:13px">Email Verification</p>
                </div>
                <div class="content">
                    <p style="font-size: 16px; margin-bottom: 8px;">Hi <strong>{name}</strong>,</p>
                    <p style="color: #94a3b8; font-size: 14px;">Use the code below to verify your email address. It expires in <strong>5 minutes</strong>.</p>
                    
                    <div class="otp-box">
                        <span class="otp-code">{otp}</span>
                    </div>
                    
                    <p class="footer">If you didn't request this, you can safely ignore this email.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    success = EmailService.send_email(to_email, subject, html)
    if not success:
        raise Exception("Failed to send OTP email via Resend API")
