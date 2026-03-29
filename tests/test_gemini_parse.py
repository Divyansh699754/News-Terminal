"""Tests for Gemini response parsing with fixtures."""

import json
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestGeminiResponseParsing:
    def test_pass1_has_required_fields(self, sample_gemini_response):
        pass1 = sample_gemini_response["pass1"]
        assert "summary" in pass1
        assert "entities" in pass1
        assert "country_tags" in pass1
        assert "relevance_score" in pass1
        assert "novelty" in pass1
        assert "impact" in pass1
        assert "priority" in pass1
        assert "weapon_category" in pass1

    def test_pass1_entities_structure(self, sample_gemini_response):
        entities = sample_gemini_response["pass1"]["entities"]
        assert "countries" in entities
        assert "weapons_systems" in entities
        assert "organizations" in entities
        assert "people" in entities
        assert isinstance(entities["countries"], list)

    def test_pass1_relevance_in_range(self, sample_gemini_response):
        score = sample_gemini_response["pass1"]["relevance_score"]
        assert 1 <= score <= 10

    def test_pass1_priority_valid(self, sample_gemini_response):
        priority = sample_gemini_response["pass1"]["priority"]
        assert priority in ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    def test_pass1_novelty_valid(self, sample_gemini_response):
        novelty = sample_gemini_response["pass1"]["novelty"]
        assert novelty in ("new", "update", "rehash")

    def test_pass2_has_required_fields(self, sample_gemini_response):
        pass2 = sample_gemini_response["pass2"]
        assert "framing_description" in pass2
        assert "loaded_language" in pass2
        assert "missing_context" in pass2
        assert "emotional_intensity" in pass2

    def test_pass2_loaded_language_is_list(self, sample_gemini_response):
        loaded = sample_gemini_response["pass2"]["loaded_language"]
        assert isinstance(loaded, list)
        assert all(isinstance(phrase, str) for phrase in loaded)

    def test_pass2_emotional_intensity_valid(self, sample_gemini_response):
        intensity = sample_gemini_response["pass2"]["emotional_intensity"]
        assert intensity in ("low", "medium", "high")
