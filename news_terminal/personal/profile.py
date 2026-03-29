"""Profile loader — reads your personal config."""

import yaml
from pathlib import Path

from news_terminal.utils.config import CONFIG_DIR
from news_terminal.utils.logger import get_logger

log = get_logger("personal.profile")

_profile = None


def load_profile() -> dict:
    global _profile
    if _profile is not None:
        return _profile

    path = CONFIG_DIR / "profile.yaml"
    if not path.exists():
        log.warning("No profile.yaml found — personal scoring disabled")
        return {}

    with open(path, encoding="utf-8") as f:
        _profile = yaml.safe_load(f) or {}

    log.info("Profile loaded: %s", _profile.get("identity", {}).get("name", "Unknown"))
    return _profile


def get_profile_summary() -> str:
    """Flatten profile into a text block for Gemini prompts."""
    p = load_profile()
    if not p:
        return ""

    parts = []
    identity = p.get("identity", {})
    parts.append(f"Name: {identity.get('name', 'Unknown')}, Role: {identity.get('role', 'Unknown')}")

    for project in p.get("building", []):
        parts.append(f"Building: {project.get('name', '')} — {project.get('description', '')} (sector: {project.get('sector', '')})")

    parts.append("Sectors: " + ", ".join(p.get("sectors", [])))
    parts.append("Goals: " + "; ".join(p.get("goals", [])))

    for threat in p.get("threats", []):
        parts.append(f"Threat: {threat}")

    context = p.get("context_notes", "")
    if context:
        parts.append(f"Context: {context.strip()}")

    return "\n".join(parts)


def get_thesis_keywords() -> dict[str, list[str]]:
    """Return thesis_id -> keywords mapping for quick matching."""
    p = load_profile()
    result = {}
    for thesis in p.get("theses", []):
        if thesis.get("status") == "active":
            result[thesis["id"]] = [kw.lower() for kw in thesis.get("keywords", [])]
    return result
