"""Gemini response schemas — used for structured JSON output."""

import typing_extensions as typing


class EntityExtraction(typing.TypedDict):
    countries: list[str]
    weapons_systems: list[str]
    organizations: list[str]
    people: list[str]


class Pass1Analysis(typing.TypedDict):
    summary: str
    entities: EntityExtraction
    country_tags: list[str]
    relevance_score: int
    novelty: str  # "new" | "update" | "rehash"
    impact: str  # "critical" | "high" | "medium" | "low"
    priority: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    weapon_category: str


class FramingAnalysis(typing.TypedDict):
    framing_description: str
    loaded_language: list[str]
    missing_context: str
    emotional_intensity: str  # "low" | "medium" | "high"
