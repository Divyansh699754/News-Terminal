"""RSS feed collector — pulls articles from all RSS sources."""

import hashlib
import time
from datetime import datetime, timezone

import feedparser
from dateutil import parser as dateparser

from news_terminal.utils.logger import get_logger

log = get_logger("collector.rss")

USER_AGENT = "NewsTerminal/1.0 (personal briefing)"


def _parse_date(entry: dict) -> str:
    for field in ("published", "updated", "created"):
        raw = entry.get(field) or entry.get(f"{field}_parsed")
        if raw:
            try:
                if isinstance(raw, str):
                    return dateparser.parse(raw).astimezone(timezone.utc).isoformat()
                # feedparser time struct
                return datetime(*raw[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                continue
    return datetime.now(timezone.utc).isoformat()


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _extract_text(entry: dict) -> str:
    if entry.get("content"):
        return entry["content"][0].get("value", "")
    return entry.get("summary", entry.get("description", ""))


def _extract_image(entry: dict) -> str | None:
    """Extract thumbnail/image URL from RSS entry (#10)."""
    # media:content or media:thumbnail
    for media in entry.get("media_content", []):
        url = media.get("url", "")
        if url and ("image" in media.get("type", "image")):
            return url
    if entry.get("media_thumbnail"):
        for thumb in entry["media_thumbnail"]:
            if thumb.get("url"):
                return thumb["url"]
    # enclosure
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image"):
            return enc.get("href") or enc.get("url")
    # og:image in content (rough check)
    return None


def collect_rss(sources: list[dict]) -> list[dict]:
    """Collect articles from all RSS-type sources."""
    rss_sources = [s for s in sources if s["type"] == "rss"]
    articles = []

    for source in rss_sources:
        try:
            log.info("Fetching RSS: %s", source["name"])
            feed = feedparser.parse(
                source["url"],
                agent=USER_AGENT,
            )

            if feed.bozo:
                log.warning("Feed parse issue for %s: %s", source["name"], feed.bozo_exception)
                if not feed.entries:
                    continue
                # Still got entries despite parse error — use them

            for entry in feed.entries:
                url = entry.get("link", "")
                if not url:
                    continue

                articles.append({
                    "id": _article_id(url),
                    "title": entry.get("title", "").strip(),
                    "url": url,
                    "source_name": source["name"],
                    "source_bias_rating": source.get("bias_rating", "unknown"),
                    "source_bias_source": source.get("bias_source", "unknown"),
                    "category": source["category"],
                    "published": _parse_date(entry),
                    "text": _extract_text(entry),
                    "text_quality": "excerpt",
                    "image_url": _extract_image(entry),
                    "cluster_id": None,
                    "dedup_method": "unique",
                })

            log.info("  Got %d entries from %s", len(feed.entries), source["name"])
            time.sleep(0.5)

        except Exception as e:
            log.error("Failed to fetch %s: %s", source["name"], e)

    log.info("RSS collection complete: %d articles from %d sources", len(articles), len(rss_sources))
    return articles
