"""Tests for the bias module."""

from news_terminal.processor.bias import get_source_bias, merge_bias


class TestBias:
    def test_known_source_lookup(self):
        result = get_source_bias("Defense One")
        assert result["source_rating"] == "center"
        assert result["source_rating_from"] == "mbfc"

    def test_unknown_source_lookup(self):
        result = get_source_bias("Unknown Random Blog")
        assert result["source_rating"] == "unknown"
        assert result["source_rating_from"] == "none"

    def test_merge_with_framing(self):
        source_bias = get_source_bias("Defense One")
        framing = {
            "framing_description": "Neutral factual reporting",
            "loaded_language": [],
            "missing_context": "None detected",
            "emotional_intensity": "low",
        }
        result = merge_bias(source_bias, framing)
        assert result["source_rating"] == "center"
        assert result["framing"] == "Neutral factual reporting"
        assert result["note"] is not None

    def test_merge_without_framing(self):
        source_bias = get_source_bias("TechCrunch")
        result = merge_bias(source_bias, None)
        assert result["source_rating"] == "center-left"
        assert result["framing"] is None
        assert result["note"] is None
