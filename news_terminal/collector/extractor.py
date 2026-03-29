"""Article full-text extraction — trafilatura primary, newspaper4k fallback."""

import time

import trafilatura

from news_terminal.utils.logger import get_logger

log = get_logger("collector.extractor")

USER_AGENT = "NewsTerminal/1.0 (personal briefing)"

# Domains where we should NOT attempt full-text extraction (paywalled)
SKIP_DOMAINS = {
    "janes.com",
    "livemint.com",
    "economictimes.indiatimes.com",
}


def _is_paywalled(url: str) -> bool:
    return any(domain in url for domain in SKIP_DOMAINS)


def extract_full_text(url: str, fallback_text: str) -> dict:
    """
    Two-tier extraction: trafilatura (primary) -> newspaper4k (fallback).
    Returns dict with 'text' and 'quality' keys.
    """
    if _is_paywalled(url):
        return {"text": fallback_text, "quality": "excerpt"}

    # Tier 1: trafilatura
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False)
            if text and len(text) > 200:
                return {"text": text, "quality": "full"}
    except Exception as e:
        log.debug("Trafilatura failed for %s: %s", url, e)

    # Tier 2: newspaper4k fallback
    try:
        from newspaper import Article

        article = Article(url)
        article.download()
        article.parse()
        if article.text and len(article.text) > 200:
            return {"text": article.text, "quality": "full"}
    except Exception as e:
        log.debug("Newspaper4k failed for %s: %s", url, e)

    # Tier 3: fall back to RSS description
    return {"text": fallback_text, "quality": "excerpt"}


def enrich_articles(articles: list[dict], delay: float = 1.0, max_extract: int = 100) -> list[dict]:
    """
    Attempt full-text extraction for articles that only have excerpts.
    Capped at max_extract to stay within time budget (#4).
    """
    candidates = [a for a in articles if a.get("text_quality") not in ("full", "ai_summary")]
    to_extract = candidates[:max_extract]

    enriched = 0
    for article in to_extract:
        result = extract_full_text(article["url"], article["text"])
        article["text"] = result["text"]
        article["text_quality"] = result["quality"]

        if result["quality"] == "full":
            enriched += 1

        time.sleep(delay)

    skipped = len(candidates) - len(to_extract)
    log.info(
        "Text extraction: enriched %d/%d articles to full text (capped at %d, skipped %d)",
        enriched, len(to_extract), max_extract, skipped,
    )
    return articles
