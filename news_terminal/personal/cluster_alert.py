"""Cross-run cluster alerting — detects when 3+ signals cluster around your sectors within 48 hours.

How it works:
  1. Each run, personal-relevant articles are grouped by matched sector keywords.
  2. Sector hit counts are persisted to state.json across runs.
  3. When a sector accumulates 3+ hits within a 48-hour window, an alert fires.
  4. Alerts are included in the decision brief and can trigger Telegram notifications.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_terminal.personal.profile import load_profile
from news_terminal.utils.config import DATA_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("personal.cluster_alert")

ALERT_FILE = DATA_DIR / "cluster_alerts.json"
CLUSTER_THRESHOLD = 10    # signals needed to trigger (3 was too sensitive)
WINDOW_HOURS = 48


def _load_alerts() -> dict:
    if ALERT_FILE.exists():
        try:
            with open(ALERT_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"sector_hits": {}, "fired_alerts": []}


def _save_alerts(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALERT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _prune_old_hits(hits: list[dict], window_hours: int = WINDOW_HOURS) -> list[dict]:
    """Remove hits older than the window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    return [h for h in hits if h.get("timestamp", "") > cutoff]


def detect_cluster_alerts(articles: list[dict]) -> list[dict]:
    """
    Check if personal-relevant articles form a 48-hour cluster around any sector.
    Returns list of alert dicts: {sector, hit_count, articles, triggered_at}.
    """
    profile = load_profile()
    if not profile:
        return []

    sectors = profile.get("sectors", [])
    state = _load_alerts()
    sector_hits = state.get("sector_hits", {})
    now = datetime.now(timezone.utc).isoformat()

    # Record hits from this run's personal articles
    personal = [a for a in articles if a.get("personal_score", 0) >= 4]

    for article in personal:
        matched_kws = set(article.get("matched_keywords", []))
        for sector in sectors:
            # Require at least 2 keyword matches to avoid noise from short common words
            sector_words = {w.lower() for w in sector.split() if len(w) > 3}
            overlap = matched_kws & sector_words
            if len(overlap) >= 2:
                if sector not in sector_hits:
                    sector_hits[sector] = []
                sector_hits[sector].append({
                    "timestamp": now,
                    "title": article.get("title", "")[:100],
                    "url": article.get("url", ""),
                })

    # Prune old hits and check thresholds
    alerts = []
    already_fired = {a.get("sector") for a in state.get("fired_alerts", [])
                     if a.get("triggered_at", "") > (datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)).isoformat()}

    for sector, hits in sector_hits.items():
        hits = _prune_old_hits(hits)
        sector_hits[sector] = hits

        if len(hits) >= CLUSTER_THRESHOLD and sector not in already_fired:
            alert = {
                "sector": sector,
                "hit_count": len(hits),
                "window_hours": WINDOW_HOURS,
                "triggered_at": now,
                "articles": [{"title": h["title"], "url": h["url"]} for h in hits[-5:]],
            }
            alerts.append(alert)
            state.setdefault("fired_alerts", []).append({
                "sector": sector,
                "triggered_at": now,
                "hit_count": len(hits),
            })
            log.warning("CLUSTER ALERT: %d signals in '%s' within %dh",
                        len(hits), sector, WINDOW_HOURS)

    # Prune old fired alerts
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS * 2)).isoformat()
    state["fired_alerts"] = [a for a in state.get("fired_alerts", []) if a.get("triggered_at", "") > cutoff]
    state["sector_hits"] = sector_hits

    _save_alerts(state)

    if not alerts:
        log.info("No cluster alerts (checked %d sectors, %d personal articles)", len(sectors), len(personal))
    return alerts
