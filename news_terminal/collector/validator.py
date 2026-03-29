"""Source health validator — checks if RSS feeds and APIs are reachable."""

import requests

from news_terminal.utils.logger import get_logger

log = get_logger("collector.validator")

USER_AGENT = "NewsTerminal/1.0 (personal briefing)"


def validate_sources(sources: list[dict]) -> dict[str, str]:
    """
    Check each source URL with a HEAD/GET request.
    Returns dict mapping source name to status: 'alive', 'degraded', 'dead'.
    """
    results = {}

    for source in sources:
        url = source.get("url")
        if not url:
            # GDELT, Guardian etc. don't have a static URL to check
            results[source["name"]] = "alive"
            continue

        try:
            resp = requests.head(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
                allow_redirects=True,
            )
            if resp.status_code < 400:
                results[source["name"]] = "alive"
                log.info("  [OK] %s", source["name"])
            elif resp.status_code < 500:
                results[source["name"]] = "degraded"
                log.warning("  [DEGRADED] %s — HTTP %d", source["name"], resp.status_code)
            else:
                results[source["name"]] = "dead"
                log.error("  [DEAD] %s — HTTP %d", source["name"], resp.status_code)
        except requests.RequestException as e:
            results[source["name"]] = "dead"
            log.error("  [DEAD] %s — %s", source["name"], e)

    alive = sum(1 for v in results.values() if v == "alive")
    log.info("Source validation: %d/%d alive", alive, len(results))
    return results
