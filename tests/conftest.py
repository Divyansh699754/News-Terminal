"""Shared test fixtures."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_articles():
    with open(FIXTURES_DIR / "sample_articles.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_gemini_response():
    with open(FIXTURES_DIR / "sample_gemini_response.json", encoding="utf-8") as f:
        return json.load(f)
