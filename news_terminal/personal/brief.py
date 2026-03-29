"""Decision brief generator — when signals cluster around your life, this tells you what to do.

Uses ONE Gemini Flash call to analyze the top personal-relevance articles
and produce a structured brief: what happened, why it matters to YOU,
3 pivots to consider, and thesis validation alerts.
"""

import json
import os
import re

from google import genai
from google.genai import types

from news_terminal.personal.profile import get_profile_summary, load_profile
from news_terminal.utils.logger import get_logger

log = get_logger("personal.brief")

BRIEF_PROMPT = """You are a personal intelligence analyst for one specific person.

THEIR PROFILE:
{profile}

THEIR ACTIVE THESES (predictions they've made about the world):
{theses}

TODAY'S TOP SIGNALS (articles most relevant to their life):
{signals}

Based on these signals and this person's profile, produce a DECISION BRIEF:

1. "headline": A single sentence — the most important thing they need to know today.

2. "three_things": An array of exactly 3 objects, each with:
   - "signal": What happened in the world (1 sentence)
   - "why_it_matters_to_you": Why this specifically affects THEM — their projects, goals, career, family (2-3 sentences, be specific and personal)
   - "pivot": One concrete action they should consider this week (1 sentence, actionable)

3. "thesis_updates": An array of objects for any theses affected by today's signals:
   - "thesis_id": the ID from their profile
   - "status": "strengthened", "weakened", or "validated" or "killed"
   - "evidence": What happened that affects this thesis (1 sentence)

4. "threat_level": "green" (business as usual), "yellow" (pay attention), or "red" (act now)

5. "threat_summary": If yellow or red, explain what specific threat emerged and what they should monitor.

Return ONLY a JSON object. No markdown.

{{"headline": "...", "three_things": [...], "thesis_updates": [...], "threat_level": "...", "threat_summary": "..."}}
"""


def generate_decision_brief(articles: list[dict], api_key: str = None) -> dict | None:
    """
    Generate a personalized decision brief from the top personal-relevance articles.
    Uses ONE Gemini Flash call. Returns the brief dict, or None if generation fails.
    """
    profile = load_profile()
    if not profile:
        log.warning("No profile — cannot generate decision brief")
        return None

    # Get top personal articles
    personal = sorted(articles, key=lambda a: a.get("personal_score", 0), reverse=True)
    top = [a for a in personal if a.get("personal_score", 0) >= 4][:10]

    if len(top) < 2:
        log.info("Fewer than 2 personal-relevance articles — skipping brief")
        return None

    # Build signals text
    signals_text = ""
    for i, a in enumerate(top):
        signals_text += f"\n{i+1}. [{a.get('source_name', '')}] {a.get('title', '')}\n"
        signals_text += f"   Summary: {a.get('summary', a.get('text', '')[:200])}\n"
        signals_text += f"   Matched theses: {', '.join(a.get('matched_theses', [])) or 'none'}\n"

    # Build theses text
    theses_text = ""
    for t in profile.get("theses", []):
        if t.get("status") == "active":
            theses_text += f"- [{t['id']}] {t['thesis']}\n"

    prompt = BRIEF_PROMPT.format(
        profile=get_profile_summary(),
        theses=theses_text or "No active theses.",
        signals=signals_text,
    )

    # Use a single Gemini Flash call
    keys = []
    for var in ("GEMINI_KEY_1", "GEMINI_KEY_2", "GEMINI_KEY_3", "GEMINI_API_KEY"):
        k = os.environ.get(var, "")
        if k:
            keys.append(k)
    key = api_key or (keys[0] if keys else "")

    if not key:
        log.warning("No API key — cannot generate brief")
        return None

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        )

        text = response.text.strip()
        text = re.sub(r"```json?\s*", "", text)
        text = re.sub(r"```", "", text)

        brief = json.loads(text)
        log.info("Decision brief generated: %s", brief.get("headline", "")[:80])
        return brief

    except Exception as e:
        log.error("Failed to generate decision brief: %s", e)
        return None
