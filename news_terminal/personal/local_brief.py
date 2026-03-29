"""Local decision brief generator — works WITHOUT Gemini.

When Gemini quota is available, brief.py produces an AI-generated brief.
When it's not, this module creates a structured brief from the raw scoring data.
The ME tab always has content.
"""

from news_terminal.personal.profile import load_profile
from news_terminal.utils.logger import get_logger

log = get_logger("personal.local_brief")


def generate_local_brief(articles: list[dict], cluster_alerts: list[dict] = None) -> dict:
    """
    Generate a decision brief from personal scoring data without any API calls.
    Returns the same schema as the Gemini brief for seamless rendering.
    """
    profile = load_profile()
    if not profile:
        return None

    # Get top personal-relevance articles
    personal = sorted(articles, key=lambda a: a.get("personal_score", 0), reverse=True)
    top = [a for a in personal if a.get("personal_score", 0) >= 4][:20]

    if len(top) < 1:
        return None

    # Determine threat level from cluster alerts
    alert_count = len(cluster_alerts or [])
    if alert_count >= 3:
        threat_level = "red"
    elif alert_count >= 1:
        threat_level = "yellow"
    else:
        threat_level = "green"

    # Build headline from the single highest-scoring article
    headline_article = top[0]
    headline = headline_article.get("title", "No signals detected")

    # Build 3 things from the top 3 unique-category articles
    three_things = []
    seen_cats = set()
    for a in top:
        cat = a.get("category", "unknown")
        if cat in seen_cats and len(three_things) < 3:
            continue
        seen_cats.add(cat)

        # Figure out why it matters to the user
        matched_kws = a.get("matched_keywords", [])
        theses = a.get("matched_theses", [])
        why_parts = []
        if matched_kws:
            why_parts.append(f"Matches your interests: {', '.join(matched_kws[:4])}")
        if theses:
            why_parts.append(f"Relevant to your thesis: {', '.join(theses)}")

        # Get the sector this maps to
        sectors = profile.get("sectors", [])
        matched_sector = None
        for sector in sectors:
            sector_words = {w.lower() for w in sector.split() if len(w) > 3}
            if sector_words & set(matched_kws):
                matched_sector = sector
                break

        why = ". ".join(why_parts) if why_parts else f"High relevance to your profile (score: {a.get('personal_score', 0)}/10)"

        three_things.append({
            "signal": a.get("title", ""),
            "why_it_matters_to_you": why,
            "pivot": f"Review this development in {matched_sector or cat.replace('_', ' ')} and assess impact on your work.",
        })

        if len(three_things) >= 3:
            break

    # Pad if we have fewer than 3
    while len(three_things) < 3 and len(top) > len(three_things):
        a = top[len(three_things)]
        three_things.append({
            "signal": a.get("title", ""),
            "why_it_matters_to_you": f"Scored {a.get('personal_score', 0)}/10 against your profile",
            "pivot": "Monitor this story for further developments.",
        })

    # Build thesis updates from matched articles
    thesis_updates = []
    seen_theses = set()
    for a in top:
        for tid in a.get("matched_theses", []):
            if tid not in seen_theses:
                seen_theses.add(tid)
                thesis_updates.append({
                    "thesis_id": tid,
                    "status": "strengthened",
                    "evidence": a.get("title", "")[:100],
                })

    # Threat summary
    threat_summary = None
    if cluster_alerts:
        sectors_hit = [a["sector"] for a in cluster_alerts]
        threat_summary = f"Cluster alerts in: {', '.join(sectors_hit)}. Multiple signals converging on your sectors within 48 hours."

    brief = {
        "headline": headline,
        "three_things": three_things,
        "thesis_updates": thesis_updates,
        "threat_level": threat_level,
        "threat_summary": threat_summary,
        "generated_by": "local",  # So the UI knows this isn't AI-generated
    }

    log.info("Local brief generated: %s (threat: %s)", headline[:60], threat_level)
    return brief
