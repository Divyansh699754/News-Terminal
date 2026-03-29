"""Configuration loader — reads settings.yaml, sources.yaml, and source_bias.json."""

import json
from pathlib import Path

import yaml

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = _BASE_DIR / "config"
DATA_DIR = _BASE_DIR / "data"
SITE_DIR = _BASE_DIR / "site"


def load_settings() -> dict:
    local = CONFIG_DIR / "settings.local.yaml"
    path = local if local.exists() else CONFIG_DIR / "settings.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources() -> list[dict]:
    with open(CONFIG_DIR / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def load_source_bias() -> dict:
    with open(CONFIG_DIR / "source_bias.json", encoding="utf-8") as f:
        return json.load(f)


def enabled_topics(settings: dict) -> dict:
    return {k: v for k, v in settings.get("topics", {}).items() if v.get("enabled")}
