"""Hybrid bias analysis — MBFC database lookup + Gemini framing analysis."""

from news_terminal.utils.config import load_source_bias
from news_terminal.utils.logger import get_logger

log = get_logger("processor.bias")

_bias_db = None


def _get_bias_db() -> dict:
    global _bias_db
    if _bias_db is None:
        _bias_db = load_source_bias()
    return _bias_db


def get_source_bias(source_name: str) -> dict:
    """Look up source bias from the static MBFC/editorial database."""
    db = _get_bias_db()
    if source_name in db:
        entry = db[source_name]
        return {
            "source_rating": entry["rating"],
            "source_rating_from": entry["source"],
            "factual_reporting": entry.get("factual", "unknown"),
        }
    return {
        "source_rating": "unknown",
        "source_rating_from": "none",
        "factual_reporting": "unknown",
    }


def merge_bias(source_bias: dict, gemini_framing: dict | None) -> dict:
    """Combine database bias rating with Gemini framing analysis."""
    result = {
        "source_rating": source_bias["source_rating"],
        "source_rating_from": source_bias["source_rating_from"],
        "framing": None,
        "loaded_language": [],
        "missing_context": None,
        "emotional_intensity": None,
        "note": None,
    }

    if gemini_framing:
        result["framing"] = gemini_framing.get("framing_description")
        result["loaded_language"] = gemini_framing.get("loaded_language", [])
        result["missing_context"] = gemini_framing.get("missing_context")
        result["emotional_intensity"] = gemini_framing.get("emotional_intensity")
        result["note"] = "Framing analysis by Gemini — treat as suggestion"

    return result
