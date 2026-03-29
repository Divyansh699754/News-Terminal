"""CLI entry point: python -m news_terminal.dedup --slot morning"""

import argparse
import json
from datetime import datetime, timezone

from news_terminal.dedup.deduplicator import ArticleDeduplicator
from news_terminal.utils.config import DATA_DIR
from news_terminal.utils.state import load_state, save_state, prune_state
from news_terminal.utils.logger import get_logger

log = get_logger("dedup")


def main():
    parser = argparse.ArgumentParser(description="News Terminal Deduplicator")
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_path = DATA_DIR / f"raw_{args.slot}_{today}.json"

    if not raw_path.exists():
        log.error("Raw articles not found: %s", raw_path)
        return

    with open(raw_path, encoding="utf-8") as f:
        articles = json.load(f)

    log.info("=== Dedup starting: %d articles ===", len(articles))

    # Load state from previous runs
    state = load_state()
    deduper = ArticleDeduplicator(
        seen_urls=state.get("seen_urls", []),
        seen_hashes=state.get("title_hashes", []),
        saved_embeddings=state.get("cluster_embeddings"),
    )

    # Run dedup
    unique_articles = deduper.deduplicate(articles)

    # Count clusters
    clusters = {}
    for a in unique_articles:
        cid = a.get("cluster_id")
        if cid:
            clusters[cid] = clusters.get(cid, 0) + 1
    for a in unique_articles:
        a["cluster_size"] = clusters.get(a.get("cluster_id"), 1)

    # Save deduped output
    output_path = DATA_DIR / f"deduped_{args.slot}_{today}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique_articles, f, indent=2, ensure_ascii=False)

    # Persist dedup state
    new_state = deduper.get_state()
    state["seen_urls"] = new_state["seen_urls"]
    state["title_hashes"] = new_state["title_hashes"]
    state = prune_state(state)
    save_state(state)

    log.info("Deduped articles saved to %s (%d articles)", output_path, len(unique_articles))
    log.info("=== Dedup complete ===")


if __name__ == "__main__":
    main()
