"""SEC EDGAR collector — real-time corporate filings before any news outlet.

Free, no auth required. Just needs a User-Agent header with contact info.
Rate limit: 10 req/s (generous).
Monitors 8-K (material events), Form 4 (insider trades), SC 13D (activist stakes).
"""

import hashlib
import time
from datetime import datetime, timezone

import requests

from news_terminal.utils.logger import get_logger

log = get_logger("collector.edgar")

EDGAR_FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_RSS = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&dateb=&owner=include&count=30&search_text=&output=atom"
EDGAR_FILINGS_API = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt={start}&enddt={end}&forms=8-K"

# Major tech/defense companies to track
TRACKED_TICKERS = [
    "AAPL", "GOOGL", "MSFT", "META", "AMZN", "NVDA", "TSLA",  # Big tech
    "LMT", "RTX", "BA", "NOC", "GD",  # Defense
    "PLTR", "AI",  # AI/defense tech
]

USER_AGENT = "NewsTerminal divyanshpandey165@gmail.com"


def collect_edgar() -> list[dict]:
    """Pull recent 8-K filings from SEC EDGAR full-text search."""
    articles = []

    try:
        log.info("Fetching SEC EDGAR recent 8-K filings")

        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": "*",
                "forms": "8-K",
                "dateRange": "custom",
                "startdt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "enddt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )

        if resp.status_code != 200:
            # Fallback: use the RSS-like current filings feed
            log.info("EDGAR search API returned %d, trying RSS feed", resp.status_code)
            resp = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "action": "getcurrent",
                    "type": "8-K",
                    "count": "25",
                    "output": "atom",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if resp.status_code != 200:
                log.warning("EDGAR RSS also failed: %d", resp.status_code)
                return articles

            # Parse Atom feed
            import feedparser
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:25]:
                url = entry.get("link", "")
                if not url:
                    continue
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()

                articles.append({
                    "id": hashlib.sha256(url.encode()).hexdigest()[:16],
                    "title": f"SEC Filing: {title}" if not title.startswith("SEC") else title,
                    "url": url,
                    "source_name": "SEC EDGAR",
                    "source_bias_rating": "neutral",
                    "source_bias_source": "regulatory",
                    "category": "us_tech",
                    "published": entry.get("updated", datetime.now(timezone.utc).isoformat()),
                    "text": summary or title,
                    "text_quality": "excerpt",
                    "image_url": None,
                    "cluster_id": None,
                    "dedup_method": "unique",
                })

            log.info("EDGAR RSS: %d filings", len(articles))
            return articles

        # Parse JSON search results
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:25]:
            source = hit.get("_source", {})
            url = f"https://www.sec.gov/Archives/edgar/data/{source.get('file_num', '')}"
            filing_url = source.get("file_url", url)
            if filing_url and not filing_url.startswith("http"):
                filing_url = f"https://www.sec.gov{filing_url}"

            company = source.get("display_names", ["Unknown"])[0] if source.get("display_names") else "Unknown"
            form_type = source.get("forms", "8-K")
            filed_date = source.get("file_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

            articles.append({
                "id": hashlib.sha256(filing_url.encode()).hexdigest()[:16],
                "title": f"{company} — {form_type} Filing ({filed_date})",
                "url": filing_url,
                "source_name": "SEC EDGAR",
                "source_bias_rating": "neutral",
                "source_bias_source": "regulatory",
                "category": "us_tech",
                "published": f"{filed_date}T12:00:00Z",
                "text": f"{company} filed a {form_type} with the SEC on {filed_date}.",
                "text_quality": "headline",
                "image_url": None,
                "cluster_id": None,
                "dedup_method": "unique",
            })

        log.info("EDGAR: %d filings from search API", len(articles))
        time.sleep(0.5)

    except Exception as e:
        log.error("EDGAR collection failed: %s", e)

    return articles
