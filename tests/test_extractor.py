"""Tests for the text extraction module."""

from news_terminal.collector.extractor import _is_paywalled


class TestExtractor:
    def test_paywalled_janes(self):
        assert _is_paywalled("https://www.janes.com/article/123") is True

    def test_paywalled_livemint(self):
        assert _is_paywalled("https://www.livemint.com/economy/some-article") is True

    def test_paywalled_economic_times(self):
        assert _is_paywalled("https://economictimes.indiatimes.com/article/123") is True

    def test_not_paywalled_defense_one(self):
        assert _is_paywalled("https://www.defenseone.com/article/123") is False

    def test_not_paywalled_techcrunch(self):
        assert _is_paywalled("https://techcrunch.com/article/123") is False
