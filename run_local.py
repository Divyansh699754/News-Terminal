"""Local runner — thin wrapper that calls the same modules as GitHub Actions.

Instead of reimplementing pipeline logic, this calls the same __main__ entry
points that the CI workflow uses, ensuring identical behavior.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from news_terminal.utils.config import load_sources, load_settings, DATA_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("main")


def _run_module(module: str, args: list[str], env_extra: dict = None):
    """Run a news_terminal module as subprocess (same as CI does)."""
    cmd = [sys.executable, "-m", module] + args
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, env=env, cwd=str(DATA_DIR.parent))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="News Terminal — Local Runner")
    parser.add_argument("--slot", choices=["morning", "evening"], default="morning")
    parser.add_argument("--dry-run", action="store_true", help="Skip email sending")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip full-text extraction")
    parser.add_argument("--skip-gemini", action="store_true", help="Skip ALL Gemini calls")
    parser.add_argument("--skip-search", action="store_true", help="Skip Gemini Search (RSS only)")
    parser.add_argument("--validate-only", action="store_true", help="Only validate source URLs")
    args = parser.parse_args()

    settings = load_settings()

    log.info("=" * 60)
    log.info("News Terminal — %s briefing", args.slot)
    log.info("=" * 60)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Build collector args
    collector_args = ["--slot", args.slot]
    if args.validate_only:
        collector_args.append("--validate-sources")
    if args.skip_extraction:
        collector_args.append("--skip-extraction")
    if args.skip_search or args.skip_gemini:
        collector_args.append("--skip-search")

    # Step 1: Collect
    log.info("--- Step 1: Collection ---")
    rc = _run_module("news_terminal.collector", collector_args)
    if args.validate_only:
        return
    if rc != 0:
        log.error("Collector failed with exit code %d", rc)

    # Step 2: Dedup
    log.info("--- Step 2: Deduplication ---")
    _run_module("news_terminal.dedup", ["--slot", args.slot])

    # Step 3: Process
    if not args.skip_gemini:
        log.info("--- Step 3: Gemini Processing ---")
        _run_module("news_terminal.processor", ["--slot", args.slot])
    else:
        # Create a processed file with fallback data
        log.info("--- Step 3: Gemini skipped — adding placeholders ---")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        deduped = DATA_DIR / f"deduped_{args.slot}_{today}.json"
        processed = DATA_DIR / f"processed_{args.slot}_{today}.json"
        if deduped.exists():
            with open(deduped, encoding="utf-8") as f:
                articles = json.load(f)
            from news_terminal.processor.bias import get_source_bias, merge_bias
            for a in articles:
                a.setdefault("summary", a.get("text", "")[:200])
                a.setdefault("relevance_score", 5)
                a.setdefault("priority", "MEDIUM")
                a.setdefault("novelty", "new")
                a.setdefault("processed_at", datetime.now(timezone.utc).isoformat())
                a.setdefault("briefing_slot", args.slot)
                if "bias" not in a:
                    a["bias"] = merge_bias(get_source_bias(a.get("source_name", "")), None)
            with open(processed, "w", encoding="utf-8") as f:
                json.dump(articles, f, indent=2, ensure_ascii=False)

    # Step 4: Generate site
    log.info("--- Step 4: Generate site ---")
    _run_module("news_terminal.generator", ["--slot", args.slot])
    _run_module("news_terminal.generator", ["--cleanup-archive"])

    # Step 5: Email
    if not args.dry_run and settings.get("delivery", {}).get("email", {}).get("enabled"):
        log.info("--- Step 5: Sending email ---")
        _run_module("news_terminal.email_sender", ["--slot", args.slot])
    else:
        log.info("--- Step 5: Email skipped ---")

    log.info("=" * 60)
    log.info("Done! Preview: cd site && python -m http.server 8080")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
