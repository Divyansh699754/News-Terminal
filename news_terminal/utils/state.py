"""State persistence — manages dedup history and run metadata between runs."""

import json
from datetime import datetime, timezone
from pathlib import Path

from news_terminal.utils.config import DATA_DIR

STATE_FILE = DATA_DIR / "state.json"


def _default_state() -> dict:
    return {
        "seen_urls": [],
        "title_hashes": [],
        "last_run": None,
        "run_count": 0,
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except (json.JSONDecodeError, ValueError):
                return _default_state()
    return _default_state()


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["run_count"] = state.get("run_count", 0) + 1
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def prune_state(state: dict, max_urls: int = 5000) -> dict:
    """Keep state from growing unbounded."""
    if len(state.get("seen_urls", [])) > max_urls:
        state["seen_urls"] = state["seen_urls"][-max_urls:]
    if len(state.get("title_hashes", [])) > max_urls:
        state["title_hashes"] = state["title_hashes"][-max_urls:]
    return state
