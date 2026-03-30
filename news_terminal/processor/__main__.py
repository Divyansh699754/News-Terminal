"""CLI entry point: python -m news_terminal.processor --slot morning

Multi-provider processing:
  Primary (ALL articles):  Cerebras Llama 3.1 8B — 1M tokens/day free
  Fallback (if Cerebras fails): Gemini Flash-Lite — 20-60 RPD
  Bias analysis (top 10):  Gemini Flash — needs world knowledge
  Search grounding:        Gemini Flash — handled in collector, not here
"""

import argparse
import json
from datetime import datetime, timezone

from news_terminal.processor.bias import get_source_bias, merge_bias
from news_terminal.utils.config import load_settings, DATA_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("processor")

MAX_BIAS = 10  # Gemini Flash calls for bias analysis


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

    # ── Init providers ──
    cerebras = None
    gemini = None

    try:
        from news_terminal.processor.cerebras import CerebrasClient
        cerebras = CerebrasClient()
    except (ValueError, ImportError) as e:
        log.warning("Cerebras unavailable: %s", e)

    try:
        from news_terminal.processor.gemini import GeminiClient, QuotaExhausted
        gemini = GeminiClient()
    except (ValueError, ImportError) as e:
        log.warning("Gemini unavailable: %s", e)

    if not cerebras and not gemini:
        log.error("No LLM providers available — adding placeholders only")

    # ── Split: Gemini Search articles already have summaries ──
    needs_summary = [a for a in articles if a.get("discovery_source") != "gemini_search"]
    has_summary = [a for a in articles if a.get("discovery_source") == "gemini_search"]

    for a in has_summary:
        a.setdefault("processed_at", datetime.now(timezone.utc).isoformat())
        a.setdefault("briefing_slot", args.slot)
        a.setdefault("entities", {})
        a.setdefault("novelty", "new")
        a.setdefault("impact", a.get("priority", "medium").lower())
        a.setdefault("weapon_category", "")

    log.info("Pass 1: %d already summarized (search), %d need processing (RSS)",
             len(has_summary), len(needs_summary))

    # ── Pass 1: Summarize with Cerebras (primary) or Gemini (fallback) ──
    processed = list(has_summary)
    cerebras_failed = False

    for i, article in enumerate(needs_summary):
        result = None

        # Try Cerebras first
        if cerebras and not cerebras_failed:
            try:
                log.info("  [%d/%d] Cerebras: %s", i + 1, len(needs_summary), article["title"][:55])
                result = cerebras.summarize(article, settings)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    log.warning("Cerebras rate limited — switching to Gemini fallback")
                    cerebras_failed = True
                else:
                    log.error("  Cerebras error: %s", e)

        # Fallback to Gemini
        if result is None and gemini:
            try:
                log.info("  [%d/%d] Gemini fallback: %s", i + 1, len(needs_summary), article["title"][:55])
                result = gemini.summarize(article, settings)
            except Exception as e:
                log.error("  Gemini fallback failed: %s", e)

        # Apply result or use text excerpt
        if result:
            article.update({
                "summary": result.get("summary", ""),
                "entities": result.get("entities", {}),
                "country_tags": result.get("country_tags", []),
                "relevance_score": result.get("relevance_score", 5),
                "novelty": result.get("novelty", "new"),
                "impact": result.get("impact", "medium"),
                "priority": result.get("priority", "MEDIUM"),
                "weapon_category": result.get("weapon_category", ""),
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "briefing_slot": args.slot,
            })
        else:
            article.update({
                "summary": article.get("text", "")[:200],
                "relevance_score": 5,
                "priority": "MEDIUM",
                "novelty": "new",
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "briefing_slot": args.slot,
            })

        processed.append(article)

    # ── Filter by relevance ──
    min_relevance = settings.get("filters", {}).get("min_relevance_score", 4)
    relevant = [a for a in processed if a.get("relevance_score", 0) >= min_relevance]
    log.info("Filtered: %d/%d meet min relevance %d", len(relevant), len(processed), min_relevance)

    # ── Pass 2: Bias analysis with Gemini Flash (top N) ──
    relevant.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)
    bias_cap = min(MAX_BIAS, len(relevant))

    if gemini:
        log.info("Pass 2: Bias analysis (Gemini Flash) on top %d", bias_cap)
        for i, article in enumerate(relevant[:bias_cap]):
            source_bias = get_source_bias(article["source_name"])
            try:
                log.info("  [%d/%d] Bias: %s", i + 1, bias_cap, article["title"][:55])
                framing = gemini.analyze_bias(article, settings)
                article["bias"] = merge_bias(source_bias, framing)
            except Exception as e:
                log.warning("  Bias failed: %s — using source-level only", e)
                article["bias"] = merge_bias(source_bias, None)
    else:
        log.info("Pass 2: Skipped (no Gemini)")

    # All remaining get source-level bias only
    for article in relevant:
        if "bias" not in article:
            article["bias"] = merge_bias(get_source_bias(article["source_name"]), None)

    # ── Personal Intelligence ──
    brief = None
    try:
        from news_terminal.personal.scorer import PersonalScorer
        from news_terminal.personal.tracker import PredictionTracker

        log.info("Pass 3: Personal scoring")
        PersonalScorer().score_all(relevant)
        tracker = PredictionTracker()
        tracker.process_articles(relevant)
    except Exception as e:
        log.error("Personal scoring failed: %s", e)

    # ── Cluster Alerts ──
    cluster_alerts = []
    try:
        from news_terminal.personal.cluster_alert import detect_cluster_alerts
        cluster_alerts = detect_cluster_alerts(relevant)
    except Exception as e:
        log.error("Cluster alerts failed: %s", e)

    # ── Decision Brief (local, no API needed) ──
    if not brief:
        try:
            from news_terminal.personal.local_brief import generate_local_brief
            brief = generate_local_brief(relevant, cluster_alerts)
        except Exception as e:
            log.error("Local brief failed: %s", e)

    # Try Gemini brief if local brief has no AI depth
    if brief and brief.get("generated_by") == "local" and gemini:
        try:
            from news_terminal.personal.brief import generate_decision_brief
            ai_brief = generate_decision_brief(relevant)
            if ai_brief:
                brief = ai_brief
        except Exception:
            pass  # Local brief is fine

    # ── Telegram alert ──
    try:
        from news_terminal.personal.telegram import send_brief_alert
        if brief and brief.get("threat_level") in ("yellow", "red"):
            send_brief_alert(brief, cluster_alerts)
        elif cluster_alerts:
            send_brief_alert({
                "threat_level": "yellow",
                "headline": f"{len(cluster_alerts)} cluster alert(s)",
                "threat_summary": ", ".join(a["sector"] for a in cluster_alerts),
                "three_things": [],
            }, cluster_alerts)
    except Exception as e:
        log.debug("Telegram: %s", e)

    # ── Save ──
    scoreboard = None
    try:
        from news_terminal.personal.tracker import PredictionTracker
        scoreboard = PredictionTracker().get_scoreboard()
    except Exception:
        pass

    output = {
        "articles": relevant,
        "brief": brief,
        "cluster_alerts": cluster_alerts,
        "thesis_scoreboard": scoreboard,
    }

    output_path = DATA_DIR / f"processed_{args.slot}_{today}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Stats ──
    if cerebras:
        cs = cerebras.get_stats()
        log.info("Cerebras: %d calls, %d tokens", cs["calls"], cs["tokens"])
    if gemini:
        gs = gemini.get_stats()
        log.info("Gemini: Flash-Lite=%d, Flash=%d, Quota errors=%d",
                 gs["flash-lite"], gs["flash"], gs["quota_errors"])
    log.info("Output: %d articles, brief=%s, alerts=%d",
             len(relevant), "yes" if brief else "no", len(cluster_alerts))
    log.info("=== Processing complete ===")


if __name__ == "__main__":
    main()
