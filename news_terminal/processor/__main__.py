"""CLI entry point: python -m news_terminal.processor --slot morning

Quota-aware processing:
  Free tier = 20 RPD per project per model.
  With 3 keys = 60 RPD. Pipeline runs 2x/day = 30 per-run budget per model.
  Budget: ~30 Flash-Lite (RSS summaries) + ~10 Flash (bias analysis).
  Gemini Search articles already have summaries — skip Pass 1 for them.
  RSS articles are ranked by text length + source priority, top N processed.
"""

import argparse
import json
from datetime import datetime, timezone

from news_terminal.processor.gemini import GeminiClient, QuotaExhausted
from news_terminal.processor.bias import get_source_bias, merge_bias
from news_terminal.utils.config import load_settings, DATA_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("processor")

# Budget caps per run (conservative — leaves margin for retries and 2x daily runs)
MAX_SUMMARIZE = 30   # Flash-Lite calls for RSS articles
MAX_BIAS = 10        # Flash calls for bias analysis


def _rank_for_processing(articles: list[dict]) -> list[dict]:
    """Rank RSS articles by quality signals to decide which get Gemini processing.
    Higher = process first. Uses text length, source type, and category spread."""
    def score(a):
        s = 0
        s += min(len(a.get("text", "")), 2000) / 200  # longer text = better input (0-10)
        if a.get("text_quality") == "full":
            s += 5  # full text articles are much more valuable to summarize
        # Spread across categories — avoid all 30 going to one category
        return s
    return sorted(articles, key=score, reverse=True)


def main():
    parser = argparse.ArgumentParser(description="News Terminal Processor")
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    args = parser.parse_args()

    settings = load_settings()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    input_path = DATA_DIR / f"deduped_{args.slot}_{today}.json"

    if not input_path.exists():
        log.error("Deduped articles not found: %s", input_path)
        return

    with open(input_path, encoding="utf-8") as f:
        articles = json.load(f)

    log.info("=== Processing starting: %d articles ===", len(articles))

    try:
        gemini = GeminiClient()
    except ValueError as e:
        log.error("Cannot init Gemini: %s — adding placeholders only", e)
        gemini = None

    # Split: Gemini Search articles already have summaries
    needs_summary = [a for a in articles if a.get("discovery_source") != "gemini_search"]
    has_summary = [a for a in articles if a.get("discovery_source") == "gemini_search"]

    for a in has_summary:
        a.setdefault("processed_at", datetime.now(timezone.utc).isoformat())
        a.setdefault("briefing_slot", args.slot)
        a.setdefault("entities", {})
        a.setdefault("novelty", "new")
        a.setdefault("impact", a.get("priority", "medium").lower())
        a.setdefault("weapon_category", "")

    # Pass 1: Summarize top N RSS articles (capped at budget)
    ranked = _rank_for_processing(needs_summary)
    to_process = ranked[:MAX_SUMMARIZE]
    to_skip = ranked[MAX_SUMMARIZE:]

    log.info("Pass 1: %d Gemini Search (skip), %d RSS to process (of %d), %d RSS skipped (budget cap)",
             len(has_summary), len(to_process), len(needs_summary), len(to_skip))

    processed = list(has_summary)
    quota_hit = False

    if gemini:
        for i, article in enumerate(to_process):
            if quota_hit:
                break
            try:
                log.info("  [%d/%d] %s", i + 1, len(to_process), article["title"][:60])
                analysis = gemini.summarize(article, settings)
                article.update({
                    "summary": analysis.get("summary", ""),
                    "entities": analysis.get("entities", {}),
                    "country_tags": analysis.get("country_tags", []),
                    "relevance_score": analysis.get("relevance_score", 5),
                    "novelty": analysis.get("novelty", "new"),
                    "impact": analysis.get("impact", "medium"),
                    "priority": analysis.get("priority", "MEDIUM"),
                    "weapon_category": analysis.get("weapon_category", ""),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "briefing_slot": args.slot,
                })
                processed.append(article)
            except QuotaExhausted:
                log.warning("Quota exhausted at article %d/%d — stopping Pass 1", i + 1, len(to_process))
                quota_hit = True
                # Add remaining unprocessed with fallback
                to_skip = to_process[i:] + to_skip
            except Exception as e:
                log.error("  Failed: %s", e)
                # Still add with fallback data
                article.update({
                    "summary": article.get("text", "")[:200],
                    "relevance_score": 5,
                    "priority": "MEDIUM",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "briefing_slot": args.slot,
                })
                processed.append(article)

    # Add skipped RSS articles with fallback data (text excerpt as summary)
    for article in to_skip:
        article.update({
            "summary": article.get("text", "")[:200],
            "relevance_score": 5,
            "priority": "MEDIUM",
            "novelty": "new",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "briefing_slot": args.slot,
        })
        processed.append(article)

    # Filter by relevance
    min_relevance = settings.get("filters", {}).get("min_relevance_score", 4)
    relevant = [a for a in processed if a.get("relevance_score", 0) >= min_relevance]
    log.info("Filtered: %d/%d articles meet min relevance %d", len(relevant), len(processed), min_relevance)

    # Pass 2: Bias analysis (top N by relevance, capped at budget)
    relevant.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)
    bias_cap = min(MAX_BIAS, len(relevant))
    top_articles = relevant[:bias_cap]

    if gemini and not quota_hit:
        log.info("Pass 2: Bias analysis on top %d articles", len(top_articles))
        for i, article in enumerate(top_articles):
            source_bias = get_source_bias(article["source_name"])
            try:
                log.info("  [%d/%d] Bias: %s", i + 1, len(top_articles), article["title"][:60])
                framing = gemini.analyze_bias(article, settings)
                article["bias"] = merge_bias(source_bias, framing)
            except QuotaExhausted:
                log.warning("Quota exhausted during bias analysis — remaining get source-level only")
                for remaining in top_articles[i:]:
                    remaining["bias"] = merge_bias(get_source_bias(remaining["source_name"]), None)
                break
            except Exception as e:
                log.error("  Bias failed: %s", e)
                article["bias"] = merge_bias(source_bias, None)
    else:
        log.info("Pass 2: Skipped (no Gemini or quota exhausted)")

    # All other articles get source-level bias only
    for article in relevant[bias_cap:]:
        if "bias" not in article:
            source_bias = get_source_bias(article["source_name"])
            article["bias"] = merge_bias(source_bias, None)
    for article in relevant[:bias_cap]:
        if "bias" not in article:
            source_bias = get_source_bias(article["source_name"])
            article["bias"] = merge_bias(source_bias, None)

    # ── Personal Intelligence: score against profile + generate brief ──
    brief = None
    try:
        from news_terminal.personal.scorer import PersonalScorer
        from news_terminal.personal.brief import generate_decision_brief
        from news_terminal.personal.local_brief import generate_local_brief
        from news_terminal.personal.tracker import PredictionTracker

        log.info("Pass 3: Personal scoring against profile")
        scorer = PersonalScorer()
        scorer.score_all(relevant)

        # Track thesis evidence
        tracker = PredictionTracker()
        tracker.process_articles(relevant)

        # Generate decision brief — try Gemini first, fall back to local
        personal_top = [a for a in relevant if a.get("personal_score", 0) >= 4]
        if personal_top:
            log.info("Generating decision brief from %d personal-relevance articles", len(personal_top))
            try:
                brief = generate_decision_brief(relevant)
            except Exception as e:
                log.warning("Gemini brief failed: %s — using local brief", e)
            if not brief:
                log.info("Using local brief generator (no Gemini needed)")
                # cluster_alerts is defined later, so generate local brief after alerts
                _generate_local = True

    except ImportError:
        log.info("Personal module not available — skipping")
    except Exception as e:
        log.error("Personal scoring failed: %s", e)

    # ── Cluster Alerts: detect 48h signal clusters around your sectors ──
    cluster_alerts = []
    try:
        from news_terminal.personal.cluster_alert import detect_cluster_alerts
        cluster_alerts = detect_cluster_alerts(relevant)
    except Exception as e:
        log.error("Cluster alert detection failed: %s", e)

    # Generate local brief if Gemini brief was unavailable
    if not brief:
        try:
            from news_terminal.personal.local_brief import generate_local_brief
            brief = generate_local_brief(relevant, cluster_alerts)
        except Exception as e:
            log.error("Local brief generation failed: %s", e)

    # Save
    output = {
        "articles": relevant,
        "brief": brief,
        "cluster_alerts": cluster_alerts,
        "thesis_scoreboard": None,
    }
    try:
        from news_terminal.personal.tracker import PredictionTracker
        output["thesis_scoreboard"] = PredictionTracker().get_scoreboard()
    except Exception:
        pass

    output_path = DATA_DIR / f"processed_{args.slot}_{today}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Telegram alert if threat level is yellow/red ──
    try:
        from news_terminal.personal.telegram import send_brief_alert
        if brief and brief.get("threat_level") in ("yellow", "red"):
            send_brief_alert(brief, cluster_alerts)
        elif cluster_alerts:
            # Also alert on cluster fires even if brief threat is green
            send_brief_alert({"threat_level": "yellow",
                              "headline": f"{len(cluster_alerts)} cluster alert(s) fired",
                              "threat_summary": ", ".join(a["sector"] for a in cluster_alerts),
                              "three_things": []}, cluster_alerts)
    except Exception as e:
        log.debug("Telegram alert skipped: %s", e)

    if gemini:
        stats = gemini.get_stats()
        log.info("Gemini calls — Flash-Lite: %d, Flash: %d, Quota errors: %d",
                 stats["flash-lite"], stats["flash"], stats["quota_errors"])
    log.info("Processed %d articles (brief: %s, alerts: %d)",
             len(relevant), "generated" if brief else "skipped", len(cluster_alerts))
    log.info("=== Processing complete ===")


if __name__ == "__main__":
    main()
