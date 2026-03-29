"""Personal relevance scorer — matches articles against your profile.

Two-tier scoring:
  Tier 1 (local, free): Keyword matching against profile sectors, theses, threats.
         Runs on ALL articles. No API cost.
  Tier 2 (Gemini, costs 1 call): Deep personalization prompt for the top articles.
         Runs on the top 3 from Tier 1. Produces the decision brief.
"""

import json
import os

from google import genai
from google.genai import types

from news_terminal.personal.profile import load_profile, get_profile_summary, get_thesis_keywords
from news_terminal.utils.logger import get_logger

log = get_logger("personal.scorer")


    # Common English words that match everything — exclude from keyword matching
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "will", "have", "been",
    "their", "about", "into", "than", "them", "most", "more", "over", "also",
    "within", "between", "through", "become", "across", "before", "after",
    "news", "new", "top", "latest", "ahead", "stay", "find", "build",
}


def _build_keyword_set(profile: dict) -> set[str]:
    """Extract meaningful keywords from profile. Excludes stopwords and short words."""
    words = set()

    for sector in profile.get("sectors", []):
        words.update(w.lower() for w in sector.split() if len(w) > 3 and w.lower() not in _STOPWORDS)

    for goal in profile.get("goals", []):
        words.update(w.lower() for w in goal.split() if len(w) > 4 and w.lower() not in _STOPWORDS)

    for threat in profile.get("threats", []):
        words.update(w.lower() for w in threat.split() if len(w) > 4 and w.lower() not in _STOPWORDS)

    for project in profile.get("building", []):
        for field in ("name", "description", "sector"):
            val = project.get(field, "")
            words.update(w.lower() for w in val.split() if len(w) > 3 and w.lower() not in _STOPWORDS)

    for thesis in profile.get("theses", []):
        if thesis.get("status") == "active":
            words.update(kw.lower() for kw in thesis.get("keywords", []) if len(kw) > 3)

    return words


class PersonalScorer:
    """Scores articles against your personal profile."""

    def __init__(self):
        self.profile = load_profile()
        self.keywords = _build_keyword_set(self.profile)
        self.thesis_keywords = get_thesis_keywords()
        log.info("Personal scorer ready: %d profile keywords, %d active theses",
                 len(self.keywords), len(self.thesis_keywords))

    def score_local(self, article: dict) -> dict:
        """
        Tier 1: Local keyword matching. Free, runs on every article.
        Returns dict with personal_score (0-10), matched_keywords, matched_theses.
        """
        text = " ".join([
            article.get("title", ""),
            article.get("summary", ""),
            article.get("text", "")[:500],
        ]).lower()

        # Match against profile keywords
        matched = [kw for kw in self.keywords if kw in text]
        score = min(len(matched) * 2, 10)

        # Check thesis matches — keywords can be multi-word phrases
        matched_theses = []
        for thesis_id, thesis_kws in self.thesis_keywords.items():
            hits = 0
            for kw in thesis_kws:
                # Multi-word: check exact phrase. Single-word: check word presence.
                if " " in kw:
                    if kw in text:
                        hits += 1
                else:
                    if kw in text.split() or kw in text:
                        hits += 1
            if hits >= 1:  # At least 1 keyword hit
                matched_theses.append(thesis_id)
                score = min(score + 3, 10)

        return {
            "personal_score": score,
            "matched_keywords": matched[:10],
            "matched_theses": matched_theses,
        }

    def score_all(self, articles: list[dict]) -> list[dict]:
        """Score all articles locally and tag them with personal relevance."""
        for article in articles:
            result = self.score_local(article)
            article["personal_score"] = result["personal_score"]
            article["matched_keywords"] = result["matched_keywords"]
            article["matched_theses"] = result["matched_theses"]

        scored = sum(1 for a in articles if a.get("personal_score", 0) > 0)
        high = sum(1 for a in articles if a.get("personal_score", 0) >= 6)
        log.info("Personal scoring: %d/%d relevant, %d high-relevance", scored, len(articles), high)
        return articles
