"""Tests for the deduplication module."""

import pytest
from news_terminal.dedup.deduplicator import ArticleDeduplicator


class TestArticleDeduplicator:
    def test_url_dedup(self):
        deduper = ArticleDeduplicator(seen_urls=["https://example.com/old"])
        articles = [
            {"url": "https://example.com/old", "title": "Old Article", "text": "Old text"},
            {"url": "https://example.com/new", "title": "New Article", "text": "New text"},
        ]
        result = deduper.deduplicate(articles)
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/new"

    def test_title_dedup(self):
        deduper = ArticleDeduplicator()
        articles = [
            {"url": "https://a.com/1", "title": "India Tests Hypersonic Missile", "text": "Test article"},
            {"url": "https://b.com/2", "title": "India Tests Hypersonic Missile", "text": "Same title different source"},
        ]
        result = deduper.deduplicate(articles)
        assert len(result) == 1

    def test_unique_articles_pass_through(self):
        deduper = ArticleDeduplicator()
        articles = [
            {"url": "https://a.com/1", "title": "AI Breakthrough in Healthcare", "text": "Article about AI in healthcare."},
            {"url": "https://b.com/2", "title": "New Space Mission Launched", "text": "Article about space exploration."},
            {"url": "https://c.com/3", "title": "Economic Growth Report", "text": "Article about economics."},
        ]
        result = deduper.deduplicate(articles)
        assert len(result) == 3

    def test_state_export(self):
        deduper = ArticleDeduplicator()
        articles = [
            {"url": "https://a.com/1", "title": "Test Article", "text": "Some content"},
        ]
        deduper.deduplicate(articles)
        state = deduper.get_state()
        assert "https://a.com/1" in state["seen_urls"]
        assert len(state["title_hashes"]) == 1

    def test_state_restore(self):
        # First run
        deduper1 = ArticleDeduplicator()
        articles = [{"url": "https://a.com/1", "title": "Test", "text": "Content"}]
        deduper1.deduplicate(articles)
        state = deduper1.get_state()

        # Second run with restored state
        deduper2 = ArticleDeduplicator(
            seen_urls=state["seen_urls"],
            seen_hashes=state["title_hashes"],
        )
        articles2 = [{"url": "https://a.com/1", "title": "Test", "text": "Content"}]
        result = deduper2.deduplicate(articles2)
        assert len(result) == 0

    def test_cluster_id_assigned(self):
        deduper = ArticleDeduplicator()
        articles = [
            {"url": "https://a.com/1", "title": "Unique Article", "text": "Unique content here"},
        ]
        result = deduper.deduplicate(articles)
        assert result[0].get("cluster_id") is not None

    def test_empty_input(self):
        deduper = ArticleDeduplicator()
        result = deduper.deduplicate([])
        assert result == []
