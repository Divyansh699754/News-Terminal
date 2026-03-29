"""Email sender — sends digest via Resend API."""

import argparse
import json
import os
from datetime import datetime, timezone

import requests

from news_terminal.generator.email_builder import build_email_html
from news_terminal.utils.config import DATA_DIR, load_settings
from news_terminal.utils.logger import get_logger

log = get_logger("email_sender")

RESEND_API = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend API."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        log.error("RESEND_API_KEY not set — cannot send email")
        return False

    try:
        resp = requests.post(
            RESEND_API,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": "News Terminal <onboarding@resend.dev>",
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )
        resp.raise_for_status()
        log.info("Email sent successfully to %s", to)
        return True
    except Exception as e:
        log.error("Failed to send email: %s", e)
        return False


def send_alert(message: str, settings: dict) -> bool:
    """Send a failure alert email."""
    to = settings.get("user", {}).get("email", "")
    if not to:
        log.error("No email configured in settings")
        return False

    html = f"""
    <div style="font-family: sans-serif; padding: 20px;">
        <h2 style="color: #dc2626;">News Terminal Alert</h2>
        <p>{message}</p>
        <p style="color: #6b7280; font-size: 12px;">
            {datetime.now(timezone.utc).isoformat()}
        </p>
    </div>
    """
    return send_email(to, f"[ALERT] News Terminal — {message[:50]}", html)


def main():
    parser = argparse.ArgumentParser(description="News Terminal Email Sender")
    parser.add_argument("--slot", choices=["morning", "evening"])
    parser.add_argument("--alert", type=str, help="Send an alert email instead of digest")
    args = parser.parse_args()

    settings = load_settings()

    if args.alert:
        send_alert(args.alert, settings)
        return

    if not args.slot:
        parser.error("--slot is required unless using --alert")

    if not settings.get("delivery", {}).get("email", {}).get("enabled", True):
        log.info("Email delivery disabled in settings")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    input_path = DATA_DIR / f"processed_{args.slot}_{today}.json"

    if not input_path.exists():
        log.error("Processed articles not found: %s", input_path)
        return

    with open(input_path, encoding="utf-8") as f:
        articles = json.load(f)

    top_n = settings.get("delivery", {}).get("email", {}).get("top_n_in_email", 5)
    to = settings["user"]["email"]

    critical = sum(1 for a in articles if a.get("priority") == "CRITICAL")
    high = sum(1 for a in articles if a.get("priority") == "HIGH")

    subject = f"News Terminal {args.slot.title()} — {today} — {critical} Critical, {high} High"
    html = build_email_html(articles[:top_n], args.slot)

    send_email(to, subject, html)


if __name__ == "__main__":
    main()
