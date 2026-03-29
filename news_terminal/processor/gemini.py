"""Gemini API client — quota-aware tiered processing with key rotation."""

import json
import os
import time

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from news_terminal.processor.schemas import FramingAnalysis, Pass1Analysis
from news_terminal.utils.logger import get_logger

log = get_logger("processor.gemini")

PASS1_PROMPT = """You are an intelligence analyst preparing a daily briefing.

Analyze this article and extract structured intelligence.

Rules:
- Summary must be exactly 2-3 sentences covering WHO, WHAT, and WHY IT MATTERS
- relevance_score: 1=tangentially related, 5=relevant, 8=important, 10=critical development
- novelty: "new"=first report, "update"=ongoing story with new facts, "rehash"=no new information
- priority: "CRITICAL"=immediate strategic impact, "HIGH"=significant, "MEDIUM"=notable, "LOW"=background
- If text_quality is "excerpt", cap relevance_score at 7 (reduced confidence)

ARTICLE:
Title: {title}
Category: {category}
Text ({text_quality}): {text}

Return a JSON object matching the provided schema."""

PASS2_PROMPT = """You are a media literacy analyst. Analyze the framing and language of this text.

Focus on:
1. Framing: Who is positioned as actor vs. subject? Is framing positive, negative, or neutral?
2. Loaded language: Quote specific phrases that carry emotional weight beyond their informational content. Most news articles have 0-2 instances. Do not flag standard journalism phrasing.
3. Missing context: What relevant counter-arguments or facts are absent?
4. Emotional intensity: "low"=standard reporting, "medium"=noticeably emotional, "high"=overtly persuasive

Do NOT guess the source. Do NOT assign a political label.
Only analyze the text itself.

TEXT:
{text}

Return a JSON object matching the provided schema."""


def _load_api_keys() -> list[str]:
    keys = []
    for var in ("GEMINI_KEY_1", "GEMINI_KEY_2", "GEMINI_KEY_3"):
        k = os.environ.get(var, "")
        if k:
            keys.append(k)
    if not keys:
        single = os.environ.get("GEMINI_API_KEY", "")
        if single:
            keys.append(single)
    return keys


class QuotaExhausted(Exception):
    """Raised when all API keys have hit their daily quota."""
    pass


class GeminiClient:
    """
    Quota-aware Gemini client with key rotation.

    Free tier reality (March 2026): 20 RPD per project per model.
    With 3 keys from different projects: 60 RPD per model.
    Pipeline runs 2x/day, so per-run budget = 30 per model.

    Budget allocation per run:
      Flash:      18 search + 10 bias = 28 (of 30 available)
      Flash-Lite: 30 summarizations     = 30 (of 30 available)
    """

    def __init__(self, api_keys: list[str] = None):
        keys = api_keys or _load_api_keys()
        if not keys:
            raise ValueError("No Gemini API keys set (GEMINI_KEY_1/2/3 or GEMINI_API_KEY)")
        self.clients = [genai.Client(api_key=k) for k in keys]
        self._key_index = 0
        self._exhausted_keys: set[int] = set()
        self.flash_lite_model = "gemini-2.5-flash-lite"
        self.flash_model = "gemini-2.5-flash"
        self.last_call_time = 0.0
        self.call_count = {"flash-lite": 0, "flash": 0, "quota_errors": 0}
        log.info("Initialized with %d API key(s)", len(self.clients))

    @property
    def quota_available(self) -> bool:
        return len(self._exhausted_keys) < len(self.clients)

    def _next_client(self) -> genai.Client:
        """Round-robin, skipping exhausted keys."""
        attempts = 0
        while attempts < len(self.clients):
            idx = self._key_index % len(self.clients)
            self._key_index += 1
            if idx not in self._exhausted_keys:
                return self.clients[idx]
            attempts += 1
        raise QuotaExhausted("All API keys exhausted")

    def _rate_limit(self, min_interval: float = 5.0):
        elapsed = time.time() - self.last_call_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_call_time = time.time()

    def _call_gemini(self, model_name: str, prompt: str, schema, temperature: float = 0.1) -> dict:
        """Single Gemini call with quota-aware error handling. No retry on 429."""
        if not self.quota_available:
            raise QuotaExhausted("All API keys exhausted")

        interval = 7.0 if "flash-lite" not in model_name else 5.0
        self._rate_limit(interval)

        client_idx = self._key_index % len(self.clients)
        try:
            client = self._next_client()
        except QuotaExhausted:
            raise

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            error_str = str(e)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                # Mark this key as exhausted, don't retry — quota won't reset mid-run
                exhausted_idx = (self._key_index - 1) % len(self.clients)
                self._exhausted_keys.add(exhausted_idx)
                self.call_count["quota_errors"] += 1
                remaining = len(self.clients) - len(self._exhausted_keys)
                log.warning("Key %d exhausted (429). %d key(s) remaining.", exhausted_idx + 1, remaining)
                if not self.quota_available:
                    raise QuotaExhausted("All API keys exhausted")
                # Retry with next key immediately
                return self._call_gemini(model_name, prompt, schema, temperature)
            raise

    def summarize(self, article: dict, settings: dict) -> dict:
        max_chars = settings.get("gemini", {}).get("max_input_chars", 4000)
        text = article.get("text", "")[:max_chars]
        prompt = PASS1_PROMPT.format(
            title=article.get("title", ""),
            category=article.get("category", ""),
            text_quality=article.get("text_quality", "excerpt"),
            text=text,
        )
        result = self._call_gemini(self.flash_lite_model, prompt, Pass1Analysis)
        self.call_count["flash-lite"] += 1
        return result

    def analyze_bias(self, article: dict, settings: dict) -> dict:
        max_chars = settings.get("gemini", {}).get("max_input_chars", 4000)
        text = article.get("text", "")[:max_chars]
        prompt = PASS2_PROMPT.format(text=text)
        result = self._call_gemini(self.flash_model, prompt, FramingAnalysis)
        self.call_count["flash"] += 1
        return result

    def get_stats(self) -> dict:
        return dict(self.call_count)
