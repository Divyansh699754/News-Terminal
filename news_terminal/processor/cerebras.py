"""Cerebras Cloud client — primary summarizer with 1M tokens/day free tier.

Why Cerebras over Gemini for summarization:
  - 1M tokens/day free (vs Gemini's dynamic 20-1000 RPD)
  - Strict JSON mode with schema validation
  - 2000 tok/s (fastest inference)
  - No cloud IP blocking (works from GitHub Actions)
  - 8K context free tier (enough for 4000-char article inputs)

Gotcha: set warm_tcp_connection=False in CI environments.
"""

import json
import os
import time

from cerebras.cloud.sdk import Cerebras
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from news_terminal.utils.logger import get_logger

log = get_logger("processor.cerebras")

SUMMARIZE_PROMPT = """You are an intelligence analyst preparing a daily briefing.

Analyze this article and extract structured intelligence.

Rules:
- summary: exactly 2-3 sentences covering WHO, WHAT, and WHY IT MATTERS
- relevance_score: integer 1-10 (1=tangential, 5=relevant, 8=important, 10=critical)
- novelty: "new" (first report), "update" (ongoing with new facts), or "rehash" (no new info)
- priority: "CRITICAL" (immediate strategic impact), "HIGH" (significant), "MEDIUM" (notable), or "LOW" (background)
- weapon_category: weapon/system type if applicable, else empty string
- country_tags: ISO 2-letter country codes mentioned
- entities: extract countries, weapons_systems, organizations, people as arrays
- If text is an excerpt, cap relevance_score at 7

ARTICLE:
Title: {title}
Category: {category}
Text ({text_quality}): {text}

Return ONLY a valid JSON object with these exact keys:
{{"summary":"...","entities":{{"countries":[],"weapons_systems":[],"organizations":[],"people":[]}},"country_tags":[],"relevance_score":5,"novelty":"new","impact":"medium","priority":"MEDIUM","weapon_category":""}}"""


class CerebrasClient:
    """Cerebras Llama 3.1 8B client — primary summarization engine."""

    def __init__(self, api_key: str = None):
        key = api_key or os.environ.get("CEREBRAS_API_KEY", "")
        if not key:
            raise ValueError("CEREBRAS_API_KEY not set")
        self.client = Cerebras(api_key=key)
        self.model = "llama-3.1-8b"
        self.last_call_time = 0.0
        self.call_count = 0
        self.token_count = 0
        log.info("Cerebras client initialized (model: %s)", self.model)

    def _rate_limit(self, min_interval: float = 2.5):
        """30 RPM = 1 req per 2s. Use 2.5s for margin."""
        elapsed = time.time() - self.last_call_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_call_time = time.time()

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def summarize(self, article: dict, settings: dict) -> dict:
        """Summarize a single article. Returns structured dict."""
        self._rate_limit()

        max_chars = settings.get("gemini", {}).get("max_input_chars", 4000)
        text = article.get("text", "")[:max_chars]

        prompt = SUMMARIZE_PROMPT.format(
            title=article.get("title", ""),
            category=article.get("category", ""),
            text_quality=article.get("text_quality", "excerpt"),
            text=text,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
        )

        self.call_count += 1
        usage = response.usage
        if usage:
            self.token_count += (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)

        text_out = response.choices[0].message.content.strip()
        return json.loads(text_out)

    def get_stats(self) -> dict:
        return {"calls": self.call_count, "tokens": self.token_count}
