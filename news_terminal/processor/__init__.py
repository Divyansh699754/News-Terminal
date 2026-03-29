"""Processor module — Gemini-powered article analysis."""

from news_terminal.processor.gemini import GeminiClient
from news_terminal.processor.bias import get_source_bias

__all__ = ["GeminiClient", "get_source_bias"]
