import os
import secrets

import resend

resend.api_key = os.getenv("RESEND_API_KEY", "")

_FROM = os.getenv("RESEND_FROM_EMAIL", "Takbo Running Coach <onboarding@resend.dev>")
_APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def send_verification_email(to_email: str, name: str, token: str) -> None:
    verify_url = f"{_APP_URL}/verify-email.html?token={token}"

    if not resend.api_key:
        print(f"\n[DEV] Verification email skipped (no RESEND_API_KEY).")
        print(f"[DEV] Verify link for {to_email}:\n      {verify_url}\n")
        return

    try:
        resend.Emails.send({
            "from": _FROM,
            "to": [to_email],
            "subject": "Verify your email — Takbo Running Coach",
            "html": f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
    <div style="background:#e85d04;padding:24px 32px;">
      <h1 style="margin:0;color:#fff;font-size:22px;letter-spacing:1px;">TAKBO RUNNING COACH</h1>
    </div>
    <div style="padding:32px;">
      <h2 style="margin:0 0 12px;color:#1a1a1a;font-size:20px;">Welcome, {name}!</h2>
      <p style="color:#555;line-height:1.6;margin:0 0 24px;">
        Thanks for signing up. Click the button below to verify your email address and start your running journey.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;background:#e85d04;color:#fff;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">
        Verify Email Address
      </a>
      <p style="color:#999;font-size:13px;margin:24px 0 0;line-height:1.5;">
        This link expires in 24 hours. If you didn't create a Takbo account, you can safely ignore this email.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0;" />
      <p style="color:#bbb;font-size:12px;margin:0;">
        Or copy this URL into your browser:<br />
        <span style="color:#e85d04;word-break:break-all;">{verify_url}</span>
      </p>
    </div>
  </div>
</body>
</html>
""",
        })
    except Exception as e:
        print(f"\n[DEV] Resend could not deliver to {to_email}: {e}")
        print(f"[DEV] Verify link:\n      {verify_url}\n")
