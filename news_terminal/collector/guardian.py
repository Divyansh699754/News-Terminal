"""The Guardian Open Platform collector — full-text articles."""

import hashlib
import os
from datetime import datetime, timezone

import requests

from news_terminal.utils.logger import get_logger

log = get_logger("collector.guardian")

GUARDIAN_API = "https://content.guardianapis.com/search"

SECTIONS = [
    ("global_defense", "world/defence-and-security"),
    ("ai_ml", "technology/artificialintelligenceai"),
    ("india_policy", "world/india"),
]


def collect_guardian() -> list[dict]:
    """Pull full-text articles from The Guardian API."""
    api_key = os.environ.get("GUARDIAN_API_KEY")
    if not api_key:
        log.warning("GUARDIAN_API_KEY not set — skipping Guardian collection")
        return []

    articles = []

    for category, section in SECTIONS:
        try:
            log.info("Guardian section: %s", section)
            resp = requests.get(
                GUARDIAN_API,
                params={
                    "api-key": api_key,
                    "section": section,
                    "show-fields": "bodyText,headline,shortUrl",
                    "page-size": "20",
                    "order-by": "newest",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("response", {}).get("results", []):
                fields = item.get("fields", {})
                url = item.get("webUrl", "")
                if not url:
                    continue

                body = fields.get("bodyText", "")
                articles.append({
                    "id": hashlib.sha256(url.encode()).hexdigest()[:16],
                    "title": item.get("webTitle", "").strip(),
                    "url": url,
                    "source_name": "The Guardian",
                    "source_bias_rating": "center-left",
                    "source_bias_source": "mbfc",
                    "category": category,
                    "published": item.get("webPublicationDate", datetime.now(timezone.utc).isoformat()),
                    "text": body if body else fields.get("headline", ""),
                    "text_quality": "full" if body and len(body) > 200 else "excerpt",
                    "cluster_id": None,
                    "dedup_method": "unique",
                })

            log.info("  Guardian %s: %d articles", section, len(data.get("response", {}).get("results", [])))

        except Exception as e:
            log.error("Guardian query failed for %s: %s", section, e)

    log.info("Guardian collection complete: %d articles", len(articles))
    return articles
