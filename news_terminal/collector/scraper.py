"""Web scraper — targeted scraping for sites without working RSS (e.g., DRDO)."""

import hashlib
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from news_terminal.utils.logger import get_logger

log = get_logger("collector.scraper")

USER_AGENT = "NewsTerminal/1.0 (personal briefing)"


def collect_drdo() -> list[dict]:
    """Scrape DRDO What's New page for recent news items."""
    # DRDO site structure changes often — try multiple known paths
    urls_to_try = [
        "https://www.drdo.gov.in/drdo/whats-new",
        "https://www.drdo.gov.in/whats-new",
        "https://www.drdo.gov.in/news",
    ]
    articles = []

    try:
        resp = None
        for url in urls_to_try:
            log.info("Trying DRDO URL: %s", url)
            try:
                resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
                if resp.status_code == 200:
                    log.info("  DRDO page found at %s", url)
                    break
            except requests.RequestException:
                continue
            resp = None

        if not resp or resp.status_code != 200:
            log.warning("DRDO: all URLs returned errors — skipping")
            return articles

        soup = BeautifulSoup(resp.text, "html.parser")

        # DRDO page structure: try multiple selectors as layout changes
        for item in soup.select("div.view-content .views-row, .news-item, article, .views-field"):
            link = item.find("a", href=True)
            if not link:
                continue

            href = link["href"]
            if not href.startswith("http"):
                href = f"https://www.drdo.gov.in{href}"

            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            # Try to find a date
            date_el = item.find("span", class_="date") or item.find("time")
            pub_date = datetime.now(timezone.utc).isoformat()
            if date_el:
                try:
                    from dateutil import parser as dateparser
                    pub_date = dateparser.parse(date_el.get_text(strip=True)).astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

            # Try to get description text
            desc_el = item.find("div", class_="field-content") or item.find("p")
            desc = desc_el.get_text(strip=True) if desc_el else title

            articles.append({
                "id": hashlib.sha256(href.encode()).hexdigest()[:16],
                "title": title,
                "url": href,
                "source_name": "DRDO News",
                "source_bias_rating": "center",
                "source_bias_source": "editorial",
                "category": "india_defense",
                "published": pub_date,
                "text": desc,
                "text_quality": "excerpt",
                "cluster_id": None,
                "dedup_method": "unique",
            })

        log.info("DRDO scraper: %d items found", len(articles))

    except Exception as e:
        log.error("DRDO scraper failed: %s", e)

    return articles
