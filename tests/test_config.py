"""Tests for configuration loading."""

import json
from pathlib import Path

import yaml
import pytest

from news_terminal.utils.config import load_settings, load_sources, load_source_bias, CONFIG_DIR


class TestConfigLoading:
    def test_settings_loads(self):
        settings = load_settings()
        assert "user" in settings
        assert "topics" in settings
        assert "filters" in settings
        assert "delivery" in settings
        assert "gemini" in settings

    def test_settings_has_required_fields(self):
        settings = load_settings()
        assert settings["user"]["name"] == "Divyansh"
        assert "email" in settings["user"]
        assert "timezone" in settings["user"]

    def test_sources_loads(self):
        sources = load_sources()
        assert isinstance(sources, list)
        assert len(sources) > 0

    def test_sources_have_required_fields(self):
        sources = load_sources()
        for source in sources:
            assert "name" in source, f"Source missing name: {source}"
            assert "type" in source, f"Source missing type: {source}"
            assert "category" in source, f"Source missing category: {source}"

    def test_rss_sources_have_urls(self):
        sources = load_sources()
        rss_sources = [s for s in sources if s["type"] == "rss"]
        for source in rss_sources:
            assert "url" in source, f"RSS source missing URL: {source['name']}"

    def test_source_bias_loads(self):
        bias = load_source_bias()
        assert isinstance(bias, dict)
        assert len(bias) > 0

    def test_source_bias_structure(self):
        bias = load_source_bias()
        for name, entry in bias.items():
            assert "rating" in entry, f"Bias entry missing rating: {name}"
            assert "source" in entry, f"Bias entry missing source: {name}"
            assert "factual" in entry, f"Bias entry missing factual: {name}"

    def test_topics_structure(self):
        settings = load_settings()
        topics = settings["topics"]
        expected = {"india_defense", "global_defense", "ai_ml", "us_tech", "india_policy", "emerging_threats"}
        assert expected == set(topics.keys())

    def test_gemini_settings(self):
        settings = load_settings()
        gemini = settings["gemini"]
        assert gemini["primary_model"] == "gemini-2.5-flash-lite"
        assert gemini["analysis_model"] == "gemini-2.5-flash"
        assert gemini["temperature"] == 0.1
