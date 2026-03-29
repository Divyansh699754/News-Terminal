"""Prediction tracker — watches your theses against real-world events.

When articles match your thesis keywords, it records the evidence.
Over time, you can see which theses are gaining or losing support.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from news_terminal.personal.profile import load_profile
from news_terminal.utils.config import DATA_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("personal.tracker")

TRACKER_FILE = DATA_DIR / "thesis_tracker.json"


class PredictionTracker:
    def __init__(self):
        self.history = self._load()

    def _load(self) -> dict:
        if TRACKER_FILE.exists():
            try:
                with open(TRACKER_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"theses": {}}

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)

    def record_evidence(self, thesis_id: str, article: dict, direction: str = "supports"):
        """Record that an article provides evidence for/against a thesis."""
        if thesis_id not in self.history["theses"]:
            self.history["theses"][thesis_id] = {
                "evidence_for": [],
                "evidence_against": [],
                "first_seen": datetime.now(timezone.utc).isoformat(),
            }

        entry = {
            "date": datetime.now(timezone.utc).isoformat(),
            "title": article.get("title", "")[:100],
            "url": article.get("url", ""),
            "source": article.get("source_name", ""),
        }

        key = "evidence_for" if direction == "supports" else "evidence_against"
        # Deduplicate by URL
        existing_urls = {e["url"] for e in self.history["theses"][thesis_id][key]}
        if entry["url"] not in existing_urls:
            self.history["theses"][thesis_id][key].append(entry)
            # Keep last 20 per direction
            self.history["theses"][thesis_id][key] = self.history["theses"][thesis_id][key][-20:]

    def get_scoreboard(self) -> list[dict]:
        """Return a summary of all tracked theses with evidence counts."""
        profile = load_profile()
        theses = {t["id"]: t for t in profile.get("theses", [])}
        scoreboard = []

        for thesis_id, data in self.history.get("theses", {}).items():
            thesis_info = theses.get(thesis_id, {})
            scoreboard.append({
                "thesis_id": thesis_id,
                "thesis": thesis_info.get("thesis", "Unknown"),
                "status": thesis_info.get("status", "active"),
                "evidence_for": len(data.get("evidence_for", [])),
                "evidence_against": len(data.get("evidence_against", [])),
                "latest_evidence": (data.get("evidence_for", []) + data.get("evidence_against", []))[-1:]
            })

        return scoreboard

    def process_articles(self, articles: list[dict]):
        """Scan articles for thesis matches and record evidence."""
        recorded = 0
        for article in articles:
            for thesis_id in article.get("matched_theses", []):
                self.record_evidence(thesis_id, article, direction="supports")
                recorded += 1

        if recorded:
            self.save()
            log.info("Recorded %d thesis evidence entries", recorded)
