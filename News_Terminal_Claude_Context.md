# News Terminal — Claude Context File

> If you're an AI reading this, here's everything you need to know about this project.
> If you're a human, this is the complete map of what was built and how it all connects.

---

## What Is This?

News Terminal is an automated personal intelligence briefing system built by Divyansh. It scans hundreds of news sources every day, runs AI summarization and bias detection, scores articles against a personal profile, generates a decision brief ("3 things that matter to YOU"), and delivers it via email, Telegram, and a web dashboard — all at $0 cost, running unattended on GitHub Actions.

**Live site:** https://divyansh699754.github.io/News-Terminal/
**Repo:** https://github.com/Divyansh699754/News-Terminal
**Runs:** Automatically at 6 AM and 6 PM EST, every day

---

## How It Works (The Pipeline)

Every run executes this sequence. Each step is a separate Python module callable via `python -m news_terminal.<module>`.

```
1. COLLECT (collector/)
   ├── Gemini Search: 18 queries via Google Search grounding → ~200-300 articles with AI summaries
   ├── RSS: 26 feeds (defense, tech, AI, policy, Reddit) → ~400 articles
   ├── SEC EDGAR: real-time corporate filings → ~20 filings
   ├── Guardian API: full-text articles (if key set)
   └── Total: ~600 raw articles

2. DEDUP (dedup/)
   ├── Layer 1: URL exact match
   ├── Layer 2: SimHash on titles (syndicated reprints)
   ├── Layer 3: MinHash on content (rewritten reprints)
   ├── Layer 4: Sentence-transformer semantic clustering (same story, different wording)
   └── Merge strategy: keeps best text quality version, carries summaries across
   └── Output: ~400-500 unique articles

3. PROCESS (processor/)
   ├── Cerebras Llama 3.1 8B: summarizes top 200 RSS articles (1M tokens/day free)
   ├── Gemini Flash-Lite: fallback if Cerebras fails
   ├── Gemini Flash: bias/framing analysis on top 10 articles
   ├── Personal scoring: matches all articles against config/profile.yaml
   ├── Thesis tracking: records evidence for/against user's predictions
   ├── Cluster alerts: detects 48h signal clusters in user's sectors
   ├── Decision brief: AI-generated (Gemini) or local fallback
   └── Telegram alert: sent if threat level is yellow or red

4. GENERATE (generator/)
   ├── Static HTML site with Ground News-inspired UI
   ├── JSON data for client-side rendering
   ├── Archive management (30-day retention)
   └── Deploy to GitHub Pages (keep_files: true)

5. NOTIFY (email_sender.py)
   ├── Email via Resend API with decision brief + top 5 articles
   └── "View Full Briefing" links to GitHub Pages site
```

---

## Project Structure

```
news_terminal/
├── collector/
│   ├── gemini_search.py    — Gemini + Google Search grounding (primary discovery)
│   ├── rss.py              — 26 RSS feeds with image extraction
│   ├── edgar.py            — SEC EDGAR corporate filings
│   ├── guardian.py          — Guardian API (full-text)
│   ├── scraper.py           — DRDO page scraper (India defense)
│   ├── extractor.py         — trafilatura + newspaper4k text extraction
│   ├── validator.py         — RSS health checks
│   └── __main__.py          — CLI: python -m news_terminal.collector --slot morning
│
├── dedup/
│   ├── deduplicator.py      — 4-layer dedup with merge strategy + cross-day embeddings
│   └── __main__.py          — CLI: python -m news_terminal.dedup --slot morning
│
├── processor/
│   ├── cerebras.py          — Cerebras Llama 3.1 8B (primary summarizer, 1M tok/day)
│   ├── gemini.py            — Gemini Flash/Flash-Lite (search, bias, fallback)
│   ├── schemas.py           — TypedDict response schemas
│   ├── bias.py              — Hybrid bias: MBFC database + Gemini framing
│   └── __main__.py          — CLI: python -m news_terminal.processor --slot morning
│
├── personal/
│   ├── profile.py           — Loads config/profile.yaml
│   ├── scorer.py            — Scores articles against user profile (local, no API)
│   ├── brief.py             — Gemini-generated decision brief (1 API call)
│   ├── local_brief.py       — Local decision brief (no API needed, always works)
│   ├── tracker.py           — Prediction/thesis tracking across runs
│   ├── cluster_alert.py     — 48h cross-run signal cluster detection
│   └── telegram.py          — Telegram Bot API alerts
│
├── generator/
│   ├── site.py              — Static site builder (Jinja2)
│   ├── archive.py           — Archive retention enforcement
│   ├── email_builder.py     — HTML email with brief + clickable links
│   ├── __main__.py          — CLI: python -m news_terminal.generator --slot morning
│   └── templates/
│       ├── index.html       — Main page with squircle SVG clip-paths
│       ├── style.css        — Ground News-inspired design + newspaper mode
│       └── app.js           — Client-side: tabs, ME tab, newspaper, clustering
│
├── email_sender.py          — Resend API client
└── utils/
    ├── config.py            — YAML/JSON config loader
    ├── state.py             — Dedup state persistence (data branch)
    └── logger.py            — Structured logging

config/
├── settings.yaml            — User prefs, topics, Gemini settings, delivery config
├── sources.yaml             — 26 RSS feeds + GDELT + Guardian
├── search_queries.yaml      — 18 Gemini Search queries (6 topics × 3 angles)
├── source_bias.json         — MBFC/editorial bias ratings for each source
└── profile.yaml             — Personal profile: sectors, goals, theses, threats

.github/workflows/
├── briefing.yml             — Main pipeline: 2x daily cron + manual trigger
├── test.yml                 — CI: pytest on push/PR
└── validate_sources.yml     — Weekly RSS health check

tests/                       — 30 tests across 6 files + fixtures
run_local.py                 — Local runner (calls same modules as CI)
```

---

## Key Design Decisions

### Multi-Provider LLM Architecture
- **Cerebras** (Llama 3.1 8B) is the primary summarizer — 1M tokens/day free, no cloud IP blocking
- **Gemini Flash** handles search grounding (irreplaceable) and bias analysis (needs world knowledge)
- **Gemini Flash-Lite** is the fallback summarizer if Cerebras fails
- If ALL providers fail, articles still appear with text excerpts — the pipeline never fully breaks

### Quota Reality
- Gemini free tier: 20 RPD per project (dynamic, can vary). With 3 keys = 60 RPD
- Cerebras free tier: 1M tokens/day, 30 RPM. Processes ~200 articles per run
- Gemini Search: 18 calls per run (6 topics × 3 queries)
- Gemini bias: 10 calls per run (top 10 articles)
- Total Gemini per run: ~29 Flash calls. Two runs/day = 58 of 60 budget

### The ME Tab
The ME tab is the personal intelligence layer. It:
1. Shows your profile (name, role, sectors, goals, what you're building)
2. Generates a decision brief: 1 headline + 3 signals that matter to YOU + 3 pivots
3. Tracks your theses/predictions against real-world events (evidence scoreboard)
4. Fires cluster alerts when 3+ signals hit your sector within 48 hours
5. Shows personal-relevance-scored articles (matched against profile keywords)

The brief is generated by Gemini when available, with a local fallback that always works.

### Bias Detection
Hybrid approach:
- **Source-level**: MBFC/AllSides ratings from `config/source_bias.json` (authoritative, human-curated)
- **Article-level**: Gemini identity-blind framing analysis (supplementary, labeled as AI-generated)
- Always shows provenance — never presents LLM judgment as ground truth

### Data Persistence
GitHub Actions runners are ephemeral. State persists via an orphan `data` branch:
- `state.json`: seen URLs, title SimHashes, cluster embeddings (for cross-day dedup)
- `thesis_tracker.json`: prediction evidence entries
- `cluster_alerts.json`: sector hit counts for 48h window

### The Newspaper Mode
A button in the toolbar renders top 20 personal articles as a broadsheet newspaper:
- Playfair Display serif fonts, column rules, justified text
- Lead story with 2-column body, secondary 2-column, compact 5×4 grid
- Priority badges on every article, sorted CRITICAL first
- Decision brief in a sidebar box

---

## Secrets (GitHub Actions)

| Secret | Service | Purpose |
|--------|---------|---------|
| `GEMINI_KEY_1` | Google AI Studio | Gemini API (search + bias) |
| `GEMINI_KEY_2` | Google AI Studio | Key rotation (project 2) |
| `GEMINI_KEY_3` | Google AI Studio | Key rotation (project 3) |
| `CEREBRAS_API_KEY` | Cerebras Cloud | Primary summarizer |
| `RESEND_API_KEY` | Resend | Email delivery |
| `TELEGRAM_BOT_TOKEN` | Telegram @BotFather | Alert bot |
| `TELEGRAM_CHAT_ID` | Telegram | Divyansh's chat ID |

---

## Running Locally

```bash
# RSS only, no AI (fast, free)
python run_local.py --slot morning --skip-gemini --dry-run

# Full pipeline with AI
export CEREBRAS_API_KEY="..." GEMINI_KEY_1="..." GEMINI_KEY_2="..." GEMINI_KEY_3="..."
python run_local.py --slot morning --dry-run

# Preview site
cd site && python -m http.server 8080

# Run tests
pytest tests/ -v --timeout=120 --ignore=tests/test_dedup.py
```

---

## Known Limitations

1. **Gemini free tier is dynamic** — can drop to 20 RPD during peak demand (December 2025 nerf)
2. **Cerebras 8K context on free tier** — long articles get truncated to 4000 chars
3. **Gemini 2.5 models deprecate June/July 2026** — need migration to 3.x
4. **simhash package may fail on Python 3.12** — fallback Simhash class handles this
5. **GDELT API always 429s from CI IPs** — disabled in the pipeline
6. **DRDO website blocks automated requests** — scraper returns 0 most of the time
7. **Sentence-transformers model (80MB)** — downloads on first CI run, cached after
8. **Resend free tier** — can only send to the account owner's email without a verified domain

---

## What NOT to Do

- Do NOT add calendar, health data, or financial pattern integrations — user explicitly rejected these
- Do NOT inflate "sources scanned" numbers — be honest about what we actually receive
- Do NOT retry on 429 RESOURCE_EXHAUSTED — the quota won't reset mid-run, just stop and use fallbacks
- Do NOT process ALL RSS articles with Cerebras — cap at 200 to fit the 35-minute timeout
- Do NOT use `force_orphan: true` for GitHub Pages deploy — it destroys the archive

---

## Timeline

- **v1.0** (March 27, 2026): Initial plan — RSS + Gemini + GitHub Actions
- **v2.0** (March 28): Added Gemini Search, expanded RSS to 28 feeds, 4-layer dedup, hybrid bias
- **v3.0** (March 28): Gemini Search as primary discovery, honest metrics, two-phase parsing
- **v3.1** (March 28): Fixed 12 review issues (archive, rate limits, merge strategy, fallbacks)
- **Personal** (March 29): ME tab, decision briefs, thesis tracking, cluster alerts, Telegram
- **Cerebras** (March 29): Multi-provider architecture, SEC EDGAR, 200-article processing cap
- **Live** (March 30): GitHub Pages enabled, automated runs confirmed working

---

## For Future Claude Sessions

If someone opens a new Claude conversation about this project:
1. Read this file first — it has everything
2. The architecture doc (`ARCHITECTURE.md`) may be outdated — this file reflects actual implementation
3. The profile is at `config/profile.yaml` — that's who the user is
4. The pipeline entry points are `__main__.py` in each module
5. `run_local.py` is a thin wrapper that calls those same modules via subprocess
6. The site is pure HTML/CSS/JS — no build step, no framework
7. State persists on the `data` branch, site deploys to `gh-pages`
