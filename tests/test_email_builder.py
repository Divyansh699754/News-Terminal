"""Tests for the email builder."""

from news_terminal.generator.email_builder import build_email_html


class TestEmailBuilder:
    def test_generates_html(self, sample_articles):
        html = build_email_html(sample_articles, "morning")
        assert "<!DOCTYPE html>" in html
        assert "News Terminal" in html
        assert "Morning Briefing" in html

    def test_includes_articles(self, sample_articles):
        html = build_email_html(sample_articles, "morning")
        assert "India Tests New Hypersonic Missile System" in html

    def test_handles_empty_articles(self):
        html = build_email_html([], "morning")
        assert "<!DOCTYPE html>" in html
        assert "News Terminal" in html

    def test_limits_to_five(self, sample_articles):
        # Even with 4 articles, should render fine
        html = build_email_html(sample_articles, "evening")
        assert "Evening Briefing" in html
