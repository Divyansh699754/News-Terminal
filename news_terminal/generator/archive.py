"""Archive management — enforces retention policy and cleans old data."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from news_terminal.utils.config import SITE_DIR, load_settings
from news_terminal.utils.logger import get_logger

log = get_logger("generator.archive")


def cleanup_archive(settings: dict = None) -> int:
    """Remove archive JSON files older than archive_days. Returns count of removed files."""
    if settings is None:
        settings = load_settings()

    archive_days = settings.get("delivery", {}).get("site", {}).get("archive_days", 30)
    archive_dir = SITE_DIR / "data" / "archive"

    if not archive_dir.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=archive_days)
    removed = 0

    for f in archive_dir.iterdir():
        if not f.suffix == ".json":
            continue
        try:
            # Filename format: 2026-03-27.json
            date_str = f.stem
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff:
                f.unlink()
                removed += 1
                log.info("Removed old archive: %s", f.name)
        except (ValueError, OSError) as e:
            log.warning("Could not process archive file %s: %s", f.name, e)

    log.info("Archive cleanup: removed %d files (retention: %d days)", removed, archive_days)
    return removed
