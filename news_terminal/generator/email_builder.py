"""Email digest builder — generates HTML email with top articles."""

from datetime import datetime, timezone


def _truncate_summary(text: str, max_len: int = 200) -> str:
    """Truncate at sentence boundary, not mid-word."""
    if not text or len(text) <= max_len:
        return text
    cut = text[:max_len].rfind(".")
    if cut > 50:
        return text[: cut + 1]
    cut = text[:max_len].rfind(" ")
    if cut > 50:
        return text[:cut] + "..."
    return text[:max_len] + "..."


def _select_diverse_top(articles: list[dict], n: int = 5) -> list[dict]:
    """Select top articles with category diversity — 1 per category first, then fill by priority."""
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    sorted_articles = sorted(
        articles,
        key=lambda a: (priority_order.get(a.get("priority", "LOW"), 3), -a.get("relevance_score", 0)),
    )

    selected = []
    seen_cats = set()

    # Round 1: top 1 per category
    for a in sorted_articles:
        cat = a.get("category", "other")
        if cat not in seen_cats:
            selected.append(a)
            seen_cats.add(cat)
        if len(selected) >= n:
            break

    # Round 2: fill remaining slots by priority
    if len(selected) < n:
        for a in sorted_articles:
            if a not in selected:
                selected.append(a)
            if len(selected) >= n:
                break

    return selected


def _find_article_url(signal: str, articles: list[dict]) -> str:
    """Fuzzy match a signal text to an article URL."""
    if not signal or not articles:
        return ""
    words = [w.lower() for w in signal.split() if len(w) > 3]
    if len(words) < 2:
        return ""
    best_url = ""
    best_score = 0
    for a in articles:
        target = f"{a.get('title', '')} {a.get('summary', '')}".lower()
        hits = sum(1 for w in words if w in target)
        score = hits / len(words)
        if score > best_score and score >= 0.4:
            best_score = score
            best_url = a.get("url", "")
    return best_url


def _build_brief_rows(brief: dict, articles: list[dict] = None) -> list[str]:
    """Build HTML rows for the decision brief section in email."""
    if not brief:
        return []
    articles = articles or []

    rows = []
    threat_color = {"green": "#16a34a", "yellow": "#ca8a04", "red": "#dc2626"}.get(brief.get("threat_level", "green"), "#6b7280")

    rows.append(f"""
    <tr>
      <td style="padding:16px; background:#f8fafc; border-bottom:2px solid #e2e8f0;">
        <span style="font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:#64748b;">YOUR BRIEF</span>
        <span style="display:inline-block; padding:2px 8px; border-radius:10px; background:{threat_color}; color:white; font-size:10px; font-weight:700; margin-left:8px;">{brief.get('threat_level', 'green').upper()}</span>
        <br>
        <div style="font-size:18px; font-weight:700; color:#0f172a; margin-top:6px; line-height:1.3;">{brief.get('headline', '')}</div>
      </td>
    </tr>""")

    for i, thing in enumerate(brief.get("three_things", [])[:3], 1):
        signal = thing.get("signal", "")
        url = _find_article_url(signal, articles)
        signal_html = f'<a href="{url}" style="color:#0f172a; text-decoration:none; font-size:14px; font-weight:600; margin-left:8px;">{signal} &rarr;</a>' if url else f'<span style="font-size:14px; font-weight:600; color:#0f172a; margin-left:8px;">{signal}</span>'
        rows.append(f"""
    <tr>
      <td style="padding:12px 16px; border-bottom:1px solid #e5e7eb;">
        <span style="display:inline-block; width:24px; height:24px; background:#0f172a; color:white; border-radius:8px; text-align:center; line-height:24px; font-size:12px; font-weight:700;">{i}</span>
        {signal_html}
        <p style="font-size:13px; color:#475569; margin:4px 0 4px 32px; line-height:1.4;">{thing.get('why_it_matters_to_you', '')}</p>
        <p style="font-size:12px; color:#16a34a; margin:0 0 0 32px; font-weight:600;">Pivot: {thing.get('pivot', '')}</p>
      </td>
    </tr>""")

    return rows


def build_email_html(articles: list[dict], slot: str, site_url: str = "", brief: dict = None) -> str:
    """Build HTML email digest with decision brief + top articles."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%B %d, %Y")

    critical = sum(1 for a in articles if a.get("priority") == "CRITICAL")
    high = sum(1 for a in articles if a.get("priority") == "HIGH")

    top = _select_diverse_top(articles, n=5)

    rows = ""
    for article in top:
        priority = article.get("priority", "MEDIUM")
        color = {"CRITICAL": "#dc2626", "HIGH": "#ea580c", "MEDIUM": "#6b7280", "LOW": "#9ca3af"}.get(priority, "#6b7280")
        bias_rating = article.get("bias", {}).get("source_rating", "unknown")
        category_label = article.get("category", "").replace("_", " ").title()
        summary = _truncate_summary(article.get("summary", ""))

        rows += f"""
        <tr>
          <td style="padding: 16px; border-bottom: 1px solid #e5e7eb;">
            <span style="display:inline-block; padding:2px 8px; border-radius:4px; background:{color}; color:white; font-size:11px; font-weight:600; text-transform:uppercase;">{priority}</span>
            <span style="color:#6b7280; font-size:12px; margin-left:8px;">{article.get('source_name', '')} &middot; {bias_rating}</span>
            <span style="display:inline-block; padding:1px 6px; border-radius:3px; background:#f3f4f6; color:#6b7280; font-size:10px; margin-left:6px; text-transform:uppercase; letter-spacing:0.05em;">{category_label}</span>
            <br>
            <a href="{article.get('url', '#')}" style="color:#111827; font-size:16px; font-weight:600; text-decoration:none; line-height:1.4;">
              {article.get('title', 'Untitled')}
            </a>
            <p style="color:#4b5563; font-size:14px; margin:6px 0 0 0; line-height:1.5;">
              {summary}
            </p>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0; padding:0; background:#f3f4f6; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px; margin:0 auto; background:white;">
    <tr>
      <td style="padding:24px; background:#111827; color:white;">
        <h1 style="margin:0; font-size:20px; font-weight:700;">News Terminal</h1>
        <p style="margin:4px 0 0 0; font-size:14px; color:#9ca3af;">
          {slot.title()} Briefing &mdash; {date_str}
        </p>
        <p style="margin:4px 0 0 0; font-size:13px; color:#6b7280;">
          {critical} Critical &middot; {high} High Priority
        </p>
      </td>
    </tr>
    {"".join(_build_brief_rows(brief, articles)) if brief else ""}
    {rows}
    <tr>
      <td style="padding:20px; text-align:center; background:#f9fafb;">
        <a href="{site_url}" style="display:inline-block; padding:10px 24px; background:#111827; color:white; text-decoration:none; border-radius:6px; font-size:14px; font-weight:600;">
          View Full Briefing &rarr;
        </a>
      </td>
    </tr>
    <tr>
      <td style="padding:16px; text-align:center; font-size:11px; color:#9ca3af;">
        News Terminal &mdash; Personal Intelligence Briefing System
      </td>
    </tr>
  </table>
</body>
</html>"""
