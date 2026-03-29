"""Collector module — pulls articles from Gemini Search, RSS, Guardian, and scrapers."""

from news_terminal.collector.rss import collect_rss
from news_terminal.collector.gdelt import collect_gdelt
from news_terminal.collector.guardian import collect_guardian
from news_terminal.collector.scraper import collect_drdo
from news_terminal.collector.extractor import extract_full_text
from news_terminal.collector.validator import validate_sources
from news_terminal.collector.gemini_search import GeminiSearchCollector

__all__ = [
    "collect_rss",
    "collect_gdelt",
    "collect_guardian",
    "collect_drdo",
    "extract_full_text",
    "validate_sources",
    "GeminiSearchCollector",
]
