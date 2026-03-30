"""Static site generator — builds HTML + JSON for GitHub Pages."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from news_terminal.utils.config import SITE_DIR, load_settings
from news_terminal.utils.logger import get_logger

log = get_logger("generator.site")

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _load_profile_for_site() -> dict | None:
    """Load profile.yaml for the ME tab display."""
    try:
        from news_terminal.personal.profile import load_profile
        p = load_profile()
        if not p:
            return None
        return {
            "name": p.get("identity", {}).get("name", ""),
            "role": p.get("identity", {}).get("role", ""),
            "building": [b.get("name", "") + " — " + b.get("description", "") for b in p.get("building", [])],
            "sectors": p.get("sectors", []),
            "goals": p.get("goals", []),
            "theses": [{"id": t["id"], "thesis": t["thesis"], "status": t.get("status", "active")}
                       for t in p.get("theses", [])],
            "threats": p.get("threats", []),
        }
    except Exception:
        return None


def generate_site(articles: list[dict], slot: str, settings: dict = None, sources_scanned: int = 0,
                   brief: dict = None, scoreboard: list = None, cluster_alerts: list = None) -> None:
    """Generate the static site from processed articles."""
    if settings is None:
        settings = load_settings()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sort: priority (CRITICAL first) -> novelty penalty -> relevance (highest first) -> recency (newest first)
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    novelty_penalty = {"new": 0, "update": 0, "rehash": 2}

    def _sort_key(a):
        pri = priority_order.get(a.get("priority", "LOW"), 3)
        pri += novelty_penalty.get(a.get("novelty", "new"), 0)  # rehash drops 2 tiers
        rel = -a.get("relevance_score", 0)
        # Negate timestamp so newer articles sort first (not oldest-first)
        try:
            ts = -datetime.fromisoformat(
                a.get("published", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00")
            ).timestamp()
        except (ValueError, TypeError):
            ts = 0
        return (pri, rel, ts)

    articles.sort(key=_sort_key)

    # Cap articles per category
    max_per_tab = settings.get("filters", {}).get("max_articles_per_tab", 25)
    category_counts = {}
    filtered = []
    for article in articles:
        cat = article.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if category_counts[cat] <= max_per_tab:
            filtered.append(article)

    # Ensure site directories exist
    data_dir = SITE_DIR / "data"
    archive_dir = data_dir / "archive"
    assets_dir = SITE_DIR / "assets"
    for d in (data_dir, archive_dir, assets_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Write JSON data
    slot_json = data_dir / f"{slot}.json"
    with open(slot_json, "w", encoding="utf-8") as f:
        json.dump({
            "slot": slot,
            "date": today,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "article_count": len(filtered),
            "sources_scanned": sources_scanned,
            "brief": brief,
            "cluster_alerts": cluster_alerts or [],
            "thesis_scoreboard": scoreboard,
            "profile": _load_profile_for_site(),
            "articles": filtered,
        }, f, indent=2, ensure_ascii=False)

    # Write archive copy — merge with existing slots (morning+evening same day)
    archive_json = archive_dir / f"{today}.json"
    existing_archive = {}
    if archive_json.exists():
        try:
            with open(archive_json, encoding="utf-8") as f:
                existing_archive = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    existing_slots = existing_archive.get("slots", {})
    existing_slots[slot] = filtered
    with open(archive_json, "w", encoding="utf-8") as f:
        json.dump({
            "date": today,
            "slots": existing_slots,
        }, f, indent=2, ensure_ascii=False)

    # Render HTML
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    topics = settings.get("topics", {})
    tabs = [
        {"id": key, "name": val.get("tab_name", key)}
        for key, val in topics.items()
        if val.get("enabled", True)
    ]
    tabs.append({"id": "all", "name": "All"})

    template = env.get_template("index.html")
    html = template.render(
        slot=slot,
        date=today,
        tabs=tabs,
        article_count=len(filtered),
        sources_scanned=sources_scanned,
        theme=settings.get("delivery", {}).get("site", {}).get("theme", "auto"),
    )
    with open(SITE_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Copy static assets
    for asset in ("style.css", "app.js"):
        src = TEMPLATE_DIR / asset
        dst = assets_dir / asset
        if src.exists():
            shutil.copy2(src, dst)

    log.info("Site generated: %d articles, slot=%s", len(filtered), slot)
