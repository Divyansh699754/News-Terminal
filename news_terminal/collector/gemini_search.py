"""Gemini-powered web search collector — uses Google Search grounding to discover articles.

Parsing strategy (#3):
  Google Search grounding cannot be combined with response_schema reliably.
  Instead we use a two-phase approach:
    Phase 1: Gemini searches the web and returns a free-text response with grounding metadata.
    Phase 2: We extract articles from TWO sources and merge:
      a) Parse the response text as a JSON array (Gemini is prompted to return JSON, but without schema enforcement).
      b) Extract grounding_chunks from metadata — these are verified URLs with titles that Gemini actually cited.
    Articles from (a) are the primary source. URLs from (b) that aren't already in (a) are added as supplementary.
    If (a) fails to parse, we fall back to (b) only.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import yaml
from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from news_terminal.utils.config import CONFIG_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("collector.gemini_search")


def _load_search_queries() -> dict:
    """Load search queries from config YAML (#12)."""
    path = CONFIG_DIR / "search_queries.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("queries", {})
    # Fallback if config missing
    log.warning("search_queries.yaml not found — using built-in defaults")
    return {
        "india_defense": ["India defense DRDO military news latest"],
        "global_defense": ["global military news missile systems weapons"],
        "ai_ml": ["artificial intelligence latest breakthroughs news"],
        "us_tech": ["Silicon Valley startup funding latest news"],
        "india_policy": ["India economy RBI policy news latest"],
    }


SEARCH_PROMPT = """You are an intelligence analyst. Search for the most important news about: {query}

Find up to {n} articles published in the last 48 hours.

For EACH article, return a JSON object with ALL of these fields:
- "title": the exact headline as published
- "url": the full URL (must be a real URL from search results)
- "source_name": the publication name (e.g., "Reuters", "The Hindu")
- "published": ISO 8601 date (e.g., "2026-03-28T10:00:00Z")
- "summary": 2-3 sentences covering WHO, WHAT, and WHY IT MATTERS. No editorializing.
- "relevance_score": integer 1-10 (1=tangential, 5=relevant, 8=important, 10=critical)
- "priority": "CRITICAL" (immediate strategic impact), "HIGH" (significant), "MEDIUM" (notable), or "LOW" (background)
- "country_tags": ISO 2-letter country codes (e.g., ["IN", "US"])
- "image_url": URL to article hero image, or null

Return ONLY a JSON array. No markdown, no explanation.

[{{"title": "India Successfully Tests Agni-5 With New Guidance System",
   "url": "https://thehindu.com/news/national/agni-5-test/article123.ece",
   "source_name": "The Hindu",
   "published": "2026-03-28T08:30:00Z",
   "summary": "India conducted a successful test of the Agni-5 ballistic missile with an upgraded indigenous ring laser gyroscope. The test validates the new guidance package developed by DRDO's Research Centre Imarat.",
   "relevance_score": 9,
   "priority": "HIGH",
   "country_tags": ["IN"],
   "image_url": null}}]

IMPORTANT: Only include real URLs from search results. Never fabricate URLs.
"""


def _domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "Unknown"


def _parse_json_response(text: str) -> list[dict]:
    """Parse Gemini response text into article list with robust fallbacks."""
    # Strip markdown code blocks
    text = re.sub(r"```json?\s*", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # Attempt 1: direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "articles" in data:
            return data["articles"]
    except json.JSONDecodeError:
        pass

    # Attempt 2: find JSON array in text
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return []


def _extract_grounding_articles(response) -> list[dict]:
    """Extract articles from grounding metadata — verified URLs Gemini actually cited."""
    articles = []
    try:
        candidate = response.candidates[0]
        if not hasattr(candidate, "grounding_metadata") or not candidate.grounding_metadata:
            return articles
        meta = candidate.grounding_metadata
        if not hasattr(meta, "grounding_chunks") or not meta.grounding_chunks:
            return articles
        for chunk in meta.grounding_chunks:
            if hasattr(chunk, "web") and chunk.web:
                url = chunk.web.uri
                title = chunk.web.title if hasattr(chunk.web, "title") else ""
                if url:
                    articles.append({
                        "title": title or "",
                        "url": url,
                        "source_name": _domain_from_url(url),
                        "from_grounding": True,
                    })
    except Exception as e:
        log.debug("Could not extract grounding metadata: %s", e)
    return articles


class GeminiSearchCollector:
    """Uses Gemini + Google Search grounding to discover and analyze articles."""

    def __init__(self, api_keys: list[str] = None):
        keys = api_keys or self._load_keys()
        if not keys:
            raise ValueError("No Gemini API keys set (GEMINI_KEY_1/2/3 or GEMINI_API_KEY)")
        self.clients = [genai.Client(api_key=k) for k in keys]
        self._key_index = 0
        self.last_call_time = 0.0
        self.call_count = 0
        self.grounding_urls_found = 0
        log.info("Search collector initialized with %d API key(s)", len(self.clients))

    @staticmethod
    def _load_keys() -> list[str]:
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

    def _next_client(self) -> genai.Client:
        client = self.clients[self._key_index % len(self.clients)]
        self._key_index += 1
        return client

    def _rate_limit(self, min_interval: float = 7.0):
        """Flash model: 10 RPM ceiling is 6s, use 7s for margin."""
        elapsed = time.time() - self.last_call_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_call_time = time.time()

    @retry(
        wait=wait_exponential(multiplier=2, min=10, max=120),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def _search(self, query: str, n: int = 20) -> list[dict]:
        """Execute a single Gemini search-grounded query. Returns parsed articles."""
        self._rate_limit()

        prompt = SEARCH_PROMPT.format(query=query, n=n)

        client = self._next_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )
        self.call_count += 1

        # Phase 1: Parse structured articles from response text
        parsed_articles = _parse_json_response(response.text)

        # Phase 2: Extract grounding metadata (verified URLs)
        grounding_articles = _extract_grounding_articles(response)
        self.grounding_urls_found += len(grounding_articles)

        # Merge: grounding URLs not already in parsed results get appended
        parsed_urls = {a.get("url", "") for a in parsed_articles}
        for ga in grounding_articles:
            if ga["url"] not in parsed_urls:
                parsed_articles.append(ga)

        return parsed_articles

    def collect_all(self, topics: dict = None) -> tuple[list[dict], int]:
        """
        Run search queries for all topics.
        Returns (articles, grounding_urls_found).
        """
        if topics is None:
            topics = _load_search_queries()

        all_articles = []
        seen_urls = set()

        for category, queries in topics.items():
            log.info("Searching topic: %s (%d queries)", category, len(queries))

            for query in queries:
                try:
                    log.info("  Query: %s", query[:60])
                    articles = self._search(query, n=20)

                    for article in articles:
                        url = article.get("url", "")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        all_articles.append({
                            "id": hashlib.sha256(url.encode()).hexdigest()[:16],
                            "title": article.get("title", "").strip(),
                            "url": url,
                            "source_name": article.get("source_name", _domain_from_url(url)),
                            "source_bias_rating": "unknown",
                            "source_bias_source": "unknown",
                            "category": category,
                            "published": article.get("published", datetime.now(timezone.utc).isoformat()),
                            "text": article.get("summary", ""),
                            "text_quality": "ai_summary" if article.get("summary") else "headline",
                            "summary": article.get("summary", ""),
                            "entities": {"countries": [], "weapons_systems": [], "organizations": [], "people": []},
                            "country_tags": article.get("country_tags", []),
                            "relevance_score": article.get("relevance_score", 5),
                            "priority": article.get("priority", "MEDIUM"),
                            "novelty": "new",
                            "impact": article.get("priority", "medium").lower(),
                            "weapon_category": "",
                            "image_url": article.get("image_url"),
                            "cluster_id": None,
                            "dedup_method": "unique",
                            "discovery_source": "gemini_search",
                        })

                    log.info("    Found %d articles", len(articles))

                except Exception as e:
                    log.error("    Search failed: %s", e)

        log.info(
            "Gemini Search complete: %d unique articles, %d grounding URLs, %d API calls",
            len(all_articles), self.grounding_urls_found, self.call_count,
        )
        return all_articles, self.grounding_urls_found
