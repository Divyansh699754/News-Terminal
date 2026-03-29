"""GDELT DOC API collector — discovers stories RSS feeds might miss."""

import hashlib
import time
from datetime import datetime, timezone

import requests

from news_terminal.utils.logger import get_logger

log = get_logger("collector.gdelt")

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

QUERIES = [
    ("india_defense", "India military OR DRDO OR Indian Navy OR Indian Air Force"),
    ("global_defense", "missile test OR arms deal OR military exercise OR drone warfare"),
    ("ai_ml", "artificial intelligence OR large language model OR machine learning"),
    ("us_tech", "Silicon Valley OR tech startup OR venture capital"),
    ("india_policy", "Indian economy OR RBI policy OR Make in India"),
]


def collect_gdelt() -> list[dict]:
    """Pull articles from GDELT DOC API across all topic queries."""
    articles = []

    for i, (category, query) in enumerate(QUERIES):
        # GDELT enforces strict rate limiting — wait 10s between requests
        if i > 0:
            time.sleep(10)

        try:
            log.info("GDELT query: %s", category)
            resp = requests.get(
                GDELT_API,
                params={
                    "query": query,
                    "mode": "artlist",
                    "maxrecords": "30",
                    "format": "json",
                    "sort": "DateDesc",
                },
                timeout=30,
            )

            if resp.status_code == 429:
                log.warning("  GDELT rate limited on %s — waiting 30s and retrying", category)
                time.sleep(30)
                resp = requests.get(
                    GDELT_API,
                    params={
                        "query": query,
                        "mode": "artlist",
                        "maxrecords": "30",
                        "format": "json",
                        "sort": "DateDesc",
                    },
                    timeout=30,
                )

            resp.raise_for_status()
            data = resp.json()

            for item in data.get("articles", []):
                url = item.get("url", "")
                if not url:
                    continue

                articles.append({
                    "id": hashlib.sha256(url.encode()).hexdigest()[:16],
                    "title": item.get("title", "").strip(),
                    "url": url,
                    "source_name": item.get("domain", "GDELT"),
                    "source_bias_rating": "unknown",
                    "source_bias_source": "unknown",
                    "category": category,
                    "published": item.get("seendate", datetime.now(timezone.utc).isoformat()),
                    "text": item.get("title", ""),
                    "text_quality": "headline",
                    "cluster_id": None,
                    "dedup_method": "unique",
                })

            log.info("  GDELT %s: %d articles", category, len(data.get("articles", [])))

        except Exception as e:
            log.error("GDELT query failed for %s: %s", category, e)

    log.info("GDELT collection complete: %d articles", len(articles))
    return articles
