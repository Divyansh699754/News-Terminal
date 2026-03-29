"""CLI entry point: python -m news_terminal.generator --slot morning"""

import argparse
import json
from datetime import datetime, timezone

from news_terminal.generator.site import generate_site
from news_terminal.generator.archive import cleanup_archive
from news_terminal.utils.config import DATA_DIR, load_settings, load_sources
from news_terminal.utils.logger import get_logger

log = get_logger("generator")


def main():
    parser = argparse.ArgumentParser(description="News Terminal Generator")
    parser.add_argument("--slot", choices=["morning", "evening"])
    parser.add_argument("--cleanup-archive", action="store_true", help="Only clean old archives")
    args = parser.parse_args()

    settings = load_settings()

    if args.cleanup_archive:
        cleanup_archive(settings)
        return

    if not args.slot:
        parser.error("--slot is required unless using --cleanup-archive")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    input_path = DATA_DIR / f"processed_{args.slot}_{today}.json"

    if not input_path.exists():
        log.error("Processed articles not found: %s", input_path)
        return

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    # Support both old format (list) and new format (dict with articles + brief)
    if isinstance(data, list):
        articles = data
        brief = None
        scoreboard = None
    else:
        articles = data.get("articles", data)
        brief = data.get("brief")
        scoreboard = data.get("thesis_scoreboard")
        cluster_alerts = data.get("cluster_alerts", [])

    rss_count = len([s for s in load_sources() if s.get("type") == "rss"])

    log.info("=== Site generation: %d articles, brief=%s ===", len(articles), "yes" if brief else "no")
    generate_site(articles, args.slot, settings, sources_scanned=rss_count,
                  brief=brief, scoreboard=scoreboard, cluster_alerts=cluster_alerts)
    cleanup_archive(settings)
    log.info("=== Site generation complete ===")


if __name__ == "__main__":
    main()
