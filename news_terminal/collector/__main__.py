"""CLI entry point: python -m news_terminal.collector --slot morning"""

import argparse
import json
import os
from datetime import datetime, timezone

from news_terminal.collector.rss import collect_rss
from news_terminal.collector.gdelt import collect_gdelt
from news_terminal.collector.guardian import collect_guardian
from news_terminal.collector.scraper import collect_drdo
from news_terminal.collector.extractor import enrich_articles
from news_terminal.collector.validator import validate_sources
from news_terminal.utils.config import load_sources, load_settings, DATA_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("collector")


def main():
    parser = argparse.ArgumentParser(description="News Terminal Collector")
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    parser.add_argument("--validate-sources", action="store_true", help="Only validate source URLs")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip full-text extraction")
    parser.add_argument("--skip-search", action="store_true", help="Skip Gemini Search")
    args = parser.parse_args()

    sources = load_sources()
    settings = load_settings()

    if args.validate_sources:
        results = validate_sources(sources)
        dead = [name for name, status in results.items() if status == "dead"]
        if dead:
            log.warning("Dead sources: %s", ", ".join(dead))
        return

    log.info("=== Collection starting: %s slot ===", args.slot)

    all_articles = []

    # Step 1A: Gemini Search (primary discovery)
    # Wrapped in try/except so RSS always runs even if search fails entirely (#8)
    if not args.skip_search and os.environ.get("GEMINI_API_KEY"):
        try:
            from news_terminal.collector.gemini_search import GeminiSearchCollector
            searcher = GeminiSearchCollector()
            search_articles, grounding_count = searcher.collect_all()
            all_articles.extend(search_articles)
            log.info("Gemini Search: %d articles, %d grounding URLs", len(search_articles), grounding_count)
        except Exception as e:
            log.error("Gemini Search failed — continuing with RSS only: %s", e)
    else:
        log.info("Gemini Search: skipped (no API key or --skip-search)")

    # Step 1B: RSS feeds (always runs — this is the reliable backbone)
    rss_articles = collect_rss(sources)
    all_articles.extend(rss_articles)

    # Step 1C: Supplementary sources (each independently failable)
    try:
        all_articles.extend(collect_guardian())
    except Exception as e:
        log.error("Guardian collection failed: %s", e)

    try:
        all_articles.extend(collect_gdelt())
    except Exception as e:
        log.error("GDELT collection failed: %s", e)

    try:
        all_articles.extend(collect_drdo())
    except Exception as e:
        log.error("DRDO scraper failed: %s", e)

    log.info("Total raw articles collected: %d", len(all_articles))

    # Text extraction — capped at 100 articles to stay within time budget (#4)
    if not args.skip_extraction:
        enrich_articles(all_articles, delay=1.0, max_extract=100)

    # Save raw output
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = DATA_DIR / f"raw_{args.slot}_{today}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, indent=2, ensure_ascii=False)

    log.info("Raw articles saved to %s", output_path)
    log.info("=== Collection complete ===")


if __name__ == "__main__":
    main()
