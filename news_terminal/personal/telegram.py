"""Telegram alert sender — pushes CRITICAL/red alerts instantly.

Setup:
  1. Message @BotFather on Telegram, create a bot, get the token
  2. Message your bot, then visit: https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Find your chat_id from the response
  4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment/secrets
"""

import os

import requests

from news_terminal.utils.logger import get_logger

log = get_logger("personal.telegram")


def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        log.debug("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
        log.info("Telegram alert sent")
        return True
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def send_brief_alert(brief: dict, cluster_alerts: list = None) -> bool:
    """Send the decision brief as a Telegram alert if threat level is yellow or red."""
    if not brief:
        return False

    threat = brief.get("threat_level", "green")
    if threat == "green":
        return False

    emoji = {"yellow": "\u26a0\ufe0f", "red": "\U0001f6a8"}.get(threat, "\u2139\ufe0f")

    lines = [
        f"{emoji} <b>News Terminal — {threat.upper()} ALERT</b>",
        "",
        f"<b>{brief.get('headline', 'No headline')}</b>",
    ]

    if brief.get("threat_summary"):
        lines.append(f"\n\u26a0\ufe0f {brief['threat_summary']}")

    for i, thing in enumerate(brief.get("three_things", []), 1):
        lines.append(f"\n<b>{i}.</b> {thing.get('signal', '')}")
        lines.append(f"   \u2192 {thing.get('pivot', '')}")

    if brief.get("thesis_updates"):
        lines.append("\n<b>Thesis updates:</b>")
        for u in brief["thesis_updates"]:
            lines.append(f"  [{u.get('status', '')}] {u.get('thesis_id', '')}: {u.get('evidence', '')}")

    if cluster_alerts:
        lines.append("\n<b>Cluster alerts:</b>")
        for a in cluster_alerts:
            lines.append(f"  \U0001f534 {a.get('hit_count', 0)} signals in {a.get('sector', '')} ({a.get('window_hours', 48)}h)")

    message = "\n".join(lines)

    # Telegram has a 4096 char limit
    if len(message) > 4000:
        message = message[:3997] + "..."

    return send_telegram(message)
