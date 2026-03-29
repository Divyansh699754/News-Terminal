# News Terminal
### Personal Intelligence Briefing System — Architecture Document
**Author:** Divyansh
**Version:** 3.1 — March 2026
**Status:** Implementation Phase

---

## 1. Project Overview

News Terminal is an automated personal intelligence briefing system. It collects news across defense, technology, geopolitics, and economic topics from Google Search (via Gemini grounding) and 28 direct RSS feeds. It runs bias detection and summarization through Google Gemini, deduplicates across sources, and delivers a clean web-based briefing with an email notification. It runs twice daily via GitHub Actions at zero cost.

### Core Problem
- Information overload — too much noise, too little signal
- Political and editorial bias is invisible to casual readers
- Relevant defense/tech/policy developments are scattered across many sources
- No existing tool combines search-powered discovery + topic curation + bias tagging + clean delivery

### Design Principles
- **Honest discovery** — Gemini sends 15 queries via Google Search and returns ~300 articles; combined with 28 direct RSS feeds. We do not know how many pages Google evaluates internally — we report what we actually receive.
- **Zero maintenance** — runs unattended on GitHub Actions
- **Bias-aware, not bias-free** — tags source lean and framing type rather than pretending objectivity exists
- **India spotlight** — India defense and policy get dedicated treatment, everything else is aggregated globally
- **Cost: $0** — free-tier everything (GitHub Actions, GitHub Pages, Gemini API, Resend, RSS)
- **Graceful degradation** — every source is independently failable; the pipeline always produces output even if every source except RSS goes down
- **Honest confidence** — never present LLM judgment as ground truth; always show provenance

### Prerequisites

Before deploying, ensure the following are in place:

| Prerequisite | Details |
|---|---|
| **Gemini API key** | Free tier from [aistudio.google.com](https://aistudio.google.com). Powers search discovery + article processing. |
| **Resend API key** | Free tier from [resend.com](https://resend.com) (100 emails/day). |
| **Resend sending domain** | Resend requires a verified sending domain for production deliverability. Without one, you use `onboarding@resend.dev` which works but has a "sent via Resend" footer and lower deliverability. If you own a domain, add the DNS records (MX, TXT for SPF/DKIM) in the Resend dashboard. If you don't own a domain, `onboarding@resend.dev` works fine for personal use. |
| **Guardian API key** | Optional. From [open-platform.theguardian.com](https://open-platform.theguardian.com). Provides full-text articles. |
| **GitHub repo** | With Actions enabled, Pages enabled (deploy from `gh-pages` branch). |

---

## 2. System Architecture — High Level

```
+---------------------------------------------------------------------------+
|                        GITHUB ACTIONS (CRON)                              |
|                    Runs 2x daily: 6:00 AM + 6:00 PM EST                  |
|                    timeout: 25 minutes                                    |
+---------------------------------------------------------------------------+
|                                                                           |
|  +-----------------------------------------------------------+           |
|  |  STEP 1A: GEMINI SEARCH (PRIMARY DISCOVERY)                |           |
|  |                                                             |           |
|  |  Gemini 2.5 Flash + Google Search Grounding                 |           |
|  |  15 queries (5 topics x 3 angles) from search_queries.yaml |           |
|  |  Returns: ~300 articles with AI summaries + grounding URLs  |           |
|  +------------------------+------------------------------------+           |
|                           |                                                |
|  +------------------------+--+  +-------------------------------+          |
|  |  STEP 1B: RSS FEEDS       |  |  STEP 1C: SUPPLEMENTARY       |          |
|  |                            |  |                                |          |
|  |  28 direct feeds           |  |  * Guardian API (full-text)    |          |
|  |  ~400 articles/run         |  |  * GDELT (event discovery)     |          |
|  |  Defense, AI, Tech,        |  |  * DRDO scraper                |          |
|  |  Policy, Reddit            |  |  Each wrapped in try/except    |          |
|  +-------------+--------------+  +---------------+----------------+          |
|                |                                  |                         |
|  +-------------v----------------------------------v-----------+            |
|  |  STEP 1D: TEXT EXTRACTION (RSS articles, capped at 100)     |            |
|  |  trafilatura -> newspaper4k -> RSS excerpt fallback         |            |
|  +------------------------+-----------------------------------+            |
|                           |                                                |
|  +------------------------v-----------------------------------+            |
|  |  STEP 2: DEDUP + MERGE (~600 raw -> ~400 unique)            |            |
|  |  Layer 1: URL exact match                                   |            |
|  |  Layer 2: SimHash on titles  (merge if better quality)      |            |
|  |  Layer 3: MinHash on content (merge if better quality)      |            |
|  |  Layer 4: Sentence-transformer semantic clustering          |            |
|  +------------------------+-----------------------------------+            |
|                           |                                                |
|  +------------------------v-----------------------------------+            |
|  |  STEP 3: PROCESS                                            |            |
|  |  * Gemini Search articles already have summaries -- SKIP    |            |
|  |  * RSS articles -> Flash-Lite summarization (5s intervals)  |            |
|  |  * Top 50 articles -> Flash bias/framing (7s intervals)     |            |
|  |  * Merge with MBFC source-level bias database               |            |
|  +------------------------+-----------------------------------+            |
|                           |                                                |
|  +------------------------v---------------+  +---------------------+       |
|  |  STEP 4: GENERATE                      |  |  STEP 5: NOTIFY     |       |
|  |  * Static HTML (Jinja2)                |->|  * Resend email      |       |
|  |  * JSON data for client-side render    |  |  * Failure alerts    |       |
|  |  * Archive management                  |  +---------------------+       |
|  |  * Deploy to GitHub Pages (keep_files) |                                |
|  +----------------------------------------+                                |
|                                                                             |
|  +-----------------------------------------------------------+            |
|  |  PERSIST STATE: Push dedup history to orphan data branch   |            |
|  +-----------------------------------------------------------+            |
|                                                                             |
+---------------------------------------------------------------------------+
                             |
            +----------------+------------------+
            v                                   v
  +-------------------+              +-------------------+
  |  GITHUB PAGES     |              |  EMAIL DIGEST     |
  |  Static News UI   |              |  via Resend API   |
  |  "Powered by      |              |  Top 5 articles   |
  |   Google Search   |              |  + link to site   |
  |   + 28 feeds"     |              |                   |
  +-------------------+              +-------------------+
```

---

## 3. Module Breakdown

### 3.1 — GEMINI SEARCH COLLECTOR (`collector/gemini_search.py`)

**The primary discovery engine.** Uses Gemini 2.5 Flash with Google Search grounding to find recent articles across the web.

#### What It Actually Does

1. Loads 15 search queries (5 topics x 3 angles) from `config/search_queries.yaml`
2. Each query is sent to Gemini with `google_search` tool enabled
3. Gemini calls Google Search, reads the results, and returns a response
4. We parse articles from the response using a two-phase strategy (see below)
5. Total: 15 API calls, typically returns ~300 unique articles

**What Google Search does internally is opaque to us.** We send 15 queries and get back ~300 articles with grounding URLs. Google evaluates its own search index to produce those results, but we have no visibility into how many pages it examined. The site header shows the actual grounding URL count — the number of verified source URLs Gemini cited — not an inflated number.

#### Two-Phase Parsing Strategy (API Limitation)

Google Search grounding **cannot be reliably combined** with `response_mime_type` / `response_schema`. When both are set, the API may ignore the search tool or return malformed responses. This is a known limitation.

The workaround is a two-phase parse:

**Phase 1 — Parse response text as JSON array:**
- The prompt asks Gemini to return a JSON array of article objects (title, url, source_name, summary, relevance_score, priority, country_tags, image_url)
- Schema is NOT enforced via `response_schema` — Gemini returns free text
- Parser strips markdown code blocks, attempts `json.loads`, falls back to regex extraction of JSON array
- If the response wraps articles in `{"articles": [...]}`, that is handled too

**Phase 2 — Extract grounding metadata:**
- `response.candidates[0].grounding_metadata.grounding_chunks` contains verified URLs with titles
- These are URLs Gemini actually cited in its response — confirmed real
- Any grounding URL not already found in Phase 1 results is appended as a supplementary article

**Fallback:** If Phase 1 fails entirely (no JSON parseable), the system falls back to Phase 2 only — still gets the verified grounding URLs.

#### Search Queries

Queries are loaded from `config/search_queries.yaml` at runtime. This means changing queries is a config change, not a code change. The file currently contains v1 queries — these should be iterated based on output quality. Queries that return too-broad or empty results should be refined.

```yaml
# config/search_queries.yaml (excerpt)
queries:
  india_defense:
    - "India defense DRDO military news latest developments this week"
    - "Indian Navy Indian Air Force new weapons procurement tests"
    - "India border security strategic partnerships defense deals"
  # ... 4 more categories, 3 queries each
```

#### Why Gemini Search

| Approach | What You Get | Download Size | Time | Rate Limits |
|---|---|---|---|---|
| GDELT bulk CSV | 1M+ records | 300-600 MB | 5-8 min | None |
| GDELT DOC API | ~150 articles | 0 | 30 sec | Aggressive 429s |
| **Gemini + Google Search** | **~300 articles with summaries** | **0** | **~2 min (15 calls)** | **250 RPD Flash** |

Gemini Search wins because:
- **Zero download** — no files to fetch, parse, or store
- **Pre-analyzed** — articles come back with summaries and relevance scores already computed
- **Quality filtering** — Gemini acts as an intelligent filter, not just a data pipe
- **Grounding verification** — cited URLs are confirmed via grounding metadata

#### API Budget

| Step | Model | Calls | RPD Budget Used |
|---|---|---|---|
| Search discovery | Flash | 15 | 15/250 = 6% |
| RSS summarization | Flash-Lite | ~200 | 200/1000 = 20% |
| Bias analysis | Flash | 50 | 50/250 = 20% |
| **Total** | | **~265** | **26% Flash, 20% Flash-Lite** |

Well within single-key free tier limits.

---

### 3.2 — RSS COLLECTOR (`collector/rss.py`)

**Reliable backbone.** 28 RSS sources provide guaranteed access to specific outlets without API dependency. RSS always runs — it is the fallback if every other source fails.

#### Source Registry — 28 Feeds Across 5 Categories

| Category | Sources | Example Feeds |
|---|---|---|
| **India Defense** (5) | The Print Defence, NDTV India, Hindustan Times, IDRW, r/IndianDefense | Direct access to Indian defense reporting |
| **Global Defense** (9) | Defense One, Breaking Defense, The War Zone, Naval News, Reuters World, BBC World, Al Jazeera, AP News, SCMP, r/CredibleDefense, r/geopolitics | Major wire services + specialized defense |
| **AI & ML** (6) | arXiv CS.AI, MIT Tech Review, The Verge AI, Wired, Ars Technica, r/MachineLearning | Academic + industry + community |
| **US Tech** (3) | TechCrunch, Hacker News (100+ pts), The Register | Startup, community, and enterprise tech |
| **India Policy** (3) | Livemint Economy, Economic Times, Business Standard | Indian business press |

Plus supplementary sources: Guardian API (full-text), GDELT (event discovery), DRDO scraper. Each supplementary source is independently wrapped in try/except — if one fails, the others still run.

#### Article Images

RSS collector extracts `image_url` from multiple tag types:
- `media:content` — if the `type` attribute contains "image"
- `media:thumbnail` — common in news RSS feeds
- `enclosure` — if the MIME type starts with "image"

Gemini Search prompt also requests `image_url` for each article. The card template displays a 64x64 thumbnail on the left side of each article card when an image is available.

#### Text Extraction

RSS feeds typically only provide excerpts. For RSS-sourced articles, a two-tier extraction pipeline attempts to get full text. **Extraction is capped at 100 articles maximum** to stay within the workflow time budget — this was the primary reason the workflow timeout was bumped from 20 to 25 minutes.

1. **trafilatura** (primary) — 93% F1 accuracy, fastest
2. **newspaper4k** (fallback) — actively maintained fork
3. **RSS excerpt** (last resort) — marked as `text_quality: "excerpt"`

Paywalled domains (Janes, Livemint, ET) are skipped — RSS excerpts used directly.

---

### 3.3 — DEDUP (`dedup/deduplicator.py`)

Four-layer deduplication handles everything from exact reprints to "same story, different angle":

| Layer | Method | What It Catches | Speed |
|---|---|---|---|
| 1 | URL exact match | Syndicated identical URLs | O(1) |
| 2 | SimHash on title (Hamming distance <= 3) | "Same headline, different outlet" | O(n) |
| 3 | MinHash + LSH on content (Jaccard 0.7) | Rewritten/paraphrased reprints | O(1) amortized |
| 4 | Sentence-transformer embedding (cosine 0.75) | Same story, completely different wording | O(n) |

Layer 4 doesn't remove articles — it assigns `cluster_id` so the UI can show "[+2 other sources]" for the same story.

Model: `all-MiniLM-L6-v2` (80MB, CPU, ~50ms/article). Cached in GitHub Actions via `actions/cache@v4` with key `st-all-MiniLM-L6-v2` at `~/.cache/torch/sentence_transformers` to avoid re-downloading 80MB every run.

#### Merge Strategy (Layers 2 and 3)

When a duplicate is detected at Layer 2 (title) or Layer 3 (content), the system attempts a **merge** instead of a simple skip. This is critical because Gemini Search and RSS often find the same article — one version may have full text while the other has an AI summary.

How it works:

1. **Pre-sort by quality:** Before dedup runs, all articles are sorted by `text_quality`: `full` > `ai_summary` > `excerpt` > `headline`. Higher-quality versions are processed first and become the "existing" version.
2. **Quality upgrade:** When a duplicate is found, if the new article has better `text_quality` than the existing one, the existing article's text is upgraded.
3. **Summary preservation:** If the existing article has an AI summary from Gemini Search but the new article has full text, both are preserved — the full text replaces the body, and the AI summary is kept.
4. **Image carry-across:** If one version has an `image_url` and the other doesn't, the image is carried to the surviving article.
5. **No match found:** If the duplicate detector fires but no good existing match is found (overlap < 40% on title words), the article is silently dropped as a normal duplicate.

---

### 3.4 — PROCESSOR (`processor/`)

#### Model Strategy — Tiered + Smart Skip

Gemini Search articles already arrive with AI-generated summaries, relevance scores, and priority tags. The processor only needs to handle RSS articles.

```
Gemini Search articles (300)  -->  SKIP Pass 1  -->  Pass 2 (top 50)
RSS articles (200)            -->  Pass 1 (Flash-Lite)  -->  Pass 2 (top 50)
```

**Pass 1 — Summarize + Extract (Flash-Lite, RSS articles only):**
- 2-3 sentence summary
- Entity extraction (countries, weapons, orgs, people)
- Relevance score (1-10), priority, novelty
- Uses Gemini native `response_schema` for guaranteed valid JSON
- Rate limit: **5-second intervals** (15 RPM ceiling = 4s minimum, 25% safety margin)

**Pass 2 — Bias & Framing (Flash, top 50 articles):**
- Identity-blind: source name stripped from input
- Framing type, loaded language, missing context, emotional intensity
- Combined with MBFC database lookup for final display
- Rate limit: **7-second intervals** (10 RPM ceiling = 6s minimum, 17% safety margin)

#### Rate Limiting

| Model | RPM Ceiling | Minimum Interval | Actual Interval | Safety Margin |
|---|---|---|---|---|
| Flash-Lite | 15 RPM | 4.0s | **5.0s** | 25% |
| Flash | 10 RPM | 6.0s | **7.0s** | 17% |

All calls use exponential backoff on failure (tenacity: 3 attempts, 10s-120s waits).

#### SDK

Uses the `google-genai` SDK (not the deprecated `google-generativeai`):

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=key)

# Pass 1/2: structured output with schema enforcement
response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Pass1Analysis,
        temperature=0.1,
    ),
)

# Search grounding: NO response_schema (incompatible with google_search tool)
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=search_prompt,
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
    ),
)
grounding = response.candidates[0].grounding_metadata
```

---

### 3.5 — BIAS DETECTION — Hybrid Approach

| Signal | Source | Reliability | Role |
|---|---|---|---|
| Source rating | MBFC / AllSides database (`config/source_bias.json`) | High — human-curated | **Primary** — always displayed |
| Framing analysis | Gemini (identity-blind) | Medium — LLM judgment | **Supplementary** — labeled as AI-generated |

LLMs are unreliable at bias detection alone (they rate identical text differently based on attributed source). The hybrid approach uses the database as ground truth and Gemini only for framing analysis of the text itself.

Display always includes provenance:
```
Source: Center-Right (via MBFC)
Framing: "Frames spending as 'investment' rather than 'cost'" (AI-generated)
```

---

### 3.6 — GENERATOR (`generator/`)

Produces static HTML + JSON for GitHub Pages. Pure HTML/CSS/JS — no build step, no framework.

The site header shows: **"Powered by Google Search + 28 direct feeds"** — along with the actual grounding URL count from the current run. No inflated source counts.

Features:
- 5 category tabs + All
- Search bar + priority filter
- Article cards with colored priority borders and 64x64 thumbnail images
- Expandable framing details
- Cluster indicators ("[+2 other sources]")
- Dark/light mode toggle
- Mobile responsive

#### Email Digest — via Resend

Subject: `News Terminal Morning — 2026-03-28 — 3 Critical, 12 High`
Body: Top 5 articles, priority badges, summaries, link to full site.
Provider: Resend (100 emails/day free).

See Prerequisites section for domain verification requirements.

---

## 4. Data Persistence

GitHub Actions runners are ephemeral. State persists via an **orphan `data` branch**:

- **What's stored:** `state.json` (seen URLs, title hashes for dedup)
- **Why orphan branch:** No bloat on `main`, no expiry (unlike artifacts), standard git ops
- **Workflow:** Restore at start, persist at end (even on failure via `if: always()`)
- **Cleanup:** Monthly force-push to prune git history

### Archive Preservation

The GitHub Pages deploy step uses `keep_files: true` instead of `force_orphan: true`. This is important because `force_orphan` creates a fresh orphan commit every deploy, which **destroys the `archive/` directory** on the `gh-pages` branch. With `keep_files: true`, existing files (including `archive/` with past briefings) are preserved between deploys. A separate cleanup step runs `--cleanup-archive` to remove archives older than 30 days.

---

## 5. Configuration

```yaml
# config/settings.yaml
user:
  name: "Divyansh"
  email: "your-email@gmail.com"
  timezone: "America/New_York"

schedule:
  morning: "06:00"
  evening: "18:00"

topics:
  india_defense:  { enabled: true, tab_name: "India Defense", spotlight: true }
  global_defense: { enabled: true, tab_name: "Global Defense", region_grouping: true }
  ai_ml:          { enabled: true, tab_name: "AI & ML" }
  us_tech:        { enabled: true, tab_name: "US Tech" }
  india_policy:   { enabled: true, tab_name: "India Policy" }

filters:
  min_relevance_score: 4
  max_articles_per_tab: 25
  dedup_window_hours: 48

gemini:
  primary_model: "gemini-2.5-flash-lite"
  analysis_model: "gemini-2.5-flash"
  top_n_for_analysis: 50
  temperature: 0.1
  max_input_chars: 4000
  min_request_interval_seconds: 4    # base; actual intervals are 5s/7s per model

delivery:
  email: { enabled: true, top_n_in_email: 5, provider: "resend" }
  site:  { enabled: true, theme: "auto", archive_days: 30 }
```

Search queries are in a separate file for easy iteration:

```yaml
# config/search_queries.yaml
# v1 queries — iterate based on output quality.
queries:
  india_defense:
    - "India defense DRDO military news latest developments this week"
    - "Indian Navy Indian Air Force new weapons procurement tests"
    - "India border security strategic partnerships defense deals"
  global_defense:
    - "global military news latest missile systems weapons developments"
    - "NATO defense operations spending military technology"
    - "drone warfare hypersonic weapons stealth aircraft naval deployments"
  ai_ml:
    - "artificial intelligence latest breakthroughs research news"
    - "large language model news open source AI developments"
    - "AI regulation policy safety new AI companies funding"
  us_tech:
    - "Silicon Valley startup funding latest news this week"
    - "US tech industry venture capital IPO acquisitions"
    - "tech regulation antitrust big tech policy changes"
  india_policy:
    - "India economy RBI policy news latest developments"
    - "Indian government economic reforms budget policy"
    - "Make in India manufacturing foreign investment trade"
```

---

## 6. GitHub Actions Workflow

```yaml
name: News Terminal Daily Briefing

on:
  schedule:
    - cron: '0 11 * * *'   # 6 AM EST (morning)
    - cron: '0 23 * * *'   # 6 PM EST (evening)
  workflow_dispatch:

concurrency:
  group: briefing
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  briefing:
    runs-on: ubuntu-latest
    timeout-minutes: 25      # Bumped from 20 — text extraction can be slow

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with: { python-version: '3.12', cache: 'pip' }

      - name: Cache sentence-transformers model   # Avoids 80MB download each run
        uses: actions/cache@v4
        with:
          path: ~/.cache/torch/sentence_transformers
          key: st-all-MiniLM-L6-v2

      - run: pip install -r requirements.txt

      - name: Restore state
        run: |
          git fetch origin data --depth=1 || echo "No data branch yet"
          mkdir -p data
          if git rev-parse origin/data >/dev/null 2>&1; then
            git checkout origin/data -- state.json 2>/dev/null \
              && mv state.json data/state.json \
              || echo '{}' > data/state.json
          else
            echo '{}' > data/state.json
          fi

      - name: Determine slot
        id: slot
        run: |
          HOUR=$(date -u +%H)
          if [ "$HOUR" -lt 15 ]; then
            echo "slot=morning" >> $GITHUB_OUTPUT
          else
            echo "slot=evening" >> $GITHUB_OUTPUT
          fi

      - name: Validate sources
        run: python -m news_terminal.collector --slot ${{ steps.slot.outputs.slot }} --validate-sources
        continue-on-error: true

      - name: Run Collector (Gemini Search + RSS)
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GUARDIAN_API_KEY: ${{ secrets.GUARDIAN_API_KEY }}
        run: python -m news_terminal.collector --slot ${{ steps.slot.outputs.slot }}

      - name: Run Deduplicator
        run: python -m news_terminal.dedup --slot ${{ steps.slot.outputs.slot }}

      - name: Run Processor
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python -m news_terminal.processor --slot ${{ steps.slot.outputs.slot }}

      - name: Generate Site
        run: python -m news_terminal.generator --slot ${{ steps.slot.outputs.slot }}

      - name: Clean old archives
        run: python -m news_terminal.generator --cleanup-archive

      - name: Deploy to GitHub Pages   # keep_files preserves archive/ between deploys
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
          keep_files: true

      - name: Send Email Digest
        env:
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
        run: python -m news_terminal.email_sender --slot ${{ steps.slot.outputs.slot }}

      - name: Persist state
        if: always()
        run: |
          git config user.name "News Terminal Bot"
          git config user.email "bot@newsterminal"
          cp data/state.json /tmp/state.json 2>/dev/null || echo '{}' > /tmp/state.json
          git stash --include-untracked || true
          git checkout --orphan data_push
          git rm -rf . 2>/dev/null || true
          cp /tmp/state.json state.json
          git add state.json
          git commit -m "State: ${{ steps.slot.outputs.slot }} $(date -u +%Y-%m-%dT%H:%M:%SZ)" || echo "No state changes"
          git push origin data_push:data --force || echo "Failed to push state"

      - name: Notify on failure
        if: failure()
        env: { RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }} }
        run: python -m news_terminal.email_sender --alert "Pipeline failed at $(date -u)" || true
```

---

## 7. Project Structure

```
news_terminal/
+-- .github/workflows/
|   +-- briefing.yml              # Main 2x daily pipeline (25 min timeout)
|   +-- test.yml                  # CI tests on push/PR
|   +-- validate_sources.yml      # Weekly RSS health check
+-- config/
|   +-- settings.yaml             # Main config (topics, models, thresholds)
|   +-- sources.yaml              # 28 RSS source definitions
|   +-- search_queries.yaml       # 15 Gemini Search queries (v1, editable)
|   +-- source_bias.json          # MBFC/editorial bias database
+-- news_terminal/
|   +-- collector/
|   |   +-- __main__.py           # CLI entry point, graceful fallback orchestration
|   |   +-- gemini_search.py      # Gemini + Google Search (two-phase parsing)
|   |   +-- rss.py                # 28 RSS feeds + image extraction
|   |   +-- gdelt.py              # GDELT DOC API (supplementary)
|   |   +-- guardian.py           # Guardian API (full-text)
|   |   +-- scraper.py            # DRDO page scraper
|   |   +-- extractor.py          # trafilatura + newspaper4k (capped at 100)
|   |   +-- validator.py          # Source health checks
|   +-- dedup/
|   |   +-- deduplicator.py       # 4-layer: URL -> SimHash -> MinHash -> semantic
|   +-- processor/
|   |   +-- gemini.py             # Gemini client (google-genai SDK, tiered rate limits)
|   |   +-- schemas.py            # TypedDict response schemas
|   |   +-- bias.py               # Hybrid: MBFC lookup + Gemini framing
|   +-- generator/
|   |   +-- site.py               # Static site builder
|   |   +-- archive.py            # Retention enforcement
|   |   +-- email_builder.py      # HTML email template
|   |   +-- templates/            # index.html, style.css, app.js
|   +-- email_sender.py           # Resend API client
|   +-- utils/
|       +-- config.py             # YAML/JSON config loader
|       +-- state.py              # Dedup state persistence
|       +-- logger.py             # Structured logging
+-- tests/
|   +-- conftest.py               # Shared fixtures (sample_articles, sample_gemini_response)
|   +-- fixtures/
|   |   +-- sample_articles.json  # Test article data
|   |   +-- sample_gemini_response.json  # Gemini response parsing fixture
|   |   +-- sample_rss.xml        # RSS feed parsing fixture
|   +-- test_config.py            # Config loading, structure validation
|   +-- test_dedup.py             # URL/title/content dedup, state export/restore
|   +-- test_bias.py              # MBFC lookup, merge with/without framing
|   +-- test_email_builder.py     # HTML generation, article inclusion
|   +-- test_extractor.py         # Paywall detection
|   +-- test_gemini_parse.py      # Fixture-based Gemini response parsing
+-- run_local.py                  # Full pipeline runner
+-- requirements.txt
+-- requirements-dev.txt          # Test dependencies (pytest, pytest-cov)
+-- ARCHITECTURE.md
```

---

## 8. Data Flow — Single Run

```
06:00 EST — GitHub Actions triggers

0. RESTORE STATE (~10s)
   +-- Pull dedup history from data branch
   +-- Restore sentence-transformers model from cache (if hit)

1A. GEMINI SEARCH (~2 min)
    +-- Load 15 queries from config/search_queries.yaml
    +-- Each query: Gemini + Google Search grounding, 7s intervals
    +-- Two-phase parse: JSON from response text + grounding metadata
    +-- Unique articles found: ~300
    +-- If Gemini Search fails entirely: log error, continue to RSS

1B. RSS FEEDS (~30s)
    +-- Pull 28 RSS feeds in sequence
    +-- Extract image_url from media:content/thumbnail/enclosure
    +-- Raw articles: ~400

1C. SUPPLEMENTARY SOURCES (~30s)
    +-- Guardian API (full-text articles) — independent try/except
    +-- GDELT DOC API (event discovery) — independent try/except
    +-- DRDO scraper — independent try/except
    +-- Any failure here is non-fatal

1D. TEXT EXTRACTION (~3 min, RSS articles only)
    +-- Capped at 100 articles (time budget constraint)
    +-- trafilatura -> newspaper4k -> RSS excerpt fallback
    +-- Paywalled domains skipped

    Total raw articles: ~600

2. DEDUP + MERGE (~30s)
   +-- Layer 1: URL exact match               -> remove ~50
   +-- Layer 2: SimHash on titles              -> merge or remove ~30
   +-- Layer 3: MinHash on content             -> merge or remove ~20
   +-- Layer 4: Semantic clustering            -> group into story clusters
   +-- Merge: better text replaces worse, images carried across
   +-- Unique articles after dedup: ~400

3. PROCESS (~8 min)
   +-- Gemini Search articles: SKIP Pass 1 (already summarized)
   +-- RSS articles (~200): Flash-Lite summarization, 1 req/5s
   +-- Filter: relevance_score >= 4            -> ~300 articles
   +-- Top 50: Flash bias/framing analysis, 1 req/7s
   +-- Remainder: MBFC database lookup only
   +-- Gemini calls: ~200 Flash-Lite + 50 Flash

4. GENERATE (~1 min)
   +-- Sort by priority -> relevance -> recency
   +-- Cap at 25 per tab (up to ~120 articles total)
   +-- Render HTML with thumbnail images, write JSON data
   +-- Clean archives > 30 days
   +-- Deploy to GitHub Pages (keep_files: true)

5. NOTIFY (~5s)
   +-- Email digest (top 5 articles) via Resend
   +-- On failure: alert email

6. PERSIST STATE (~10s)
   +-- Push dedup history to data branch

Total runtime: ~16 minutes
Articles in briefing: ~120
Gemini API calls: ~265 (well within free tier)
Total cost: $0
```

---

## 9. Graceful Degradation

The pipeline is designed so that no single source failure kills the run:

| What Fails | What Happens | Output Impact |
|---|---|---|
| Gemini Search | Caught by try/except in `__main__.py`. RSS still runs. | Fewer articles (~400 instead of ~600), no AI pre-summaries |
| Guardian API | Caught independently. Other sources unaffected. | Lose ~20 full-text articles |
| GDELT | Caught independently. Other sources unaffected. | Lose supplementary event data |
| DRDO scraper | Caught independently. Other sources unaffected. | Lose DRDO-specific articles |
| Individual RSS feed | Each feed is in its own try/except. | Lose that one feed's articles |
| Text extraction | Capped at 100. Failures return excerpt. | Some articles have excerpt instead of full text |
| Sentence-transformers | Lazy-loaded, ImportError caught. | Layer 4 clustering disabled, Layers 1-3 still work |
| Resend email | Separate step. Site still deploys. | No email, but site is live |

The only truly required component is RSS — as long as at least one RSS feed responds, the pipeline produces output.

---

## 10. Testing

### Test Suite — 37 Tests Across 6 Files

| Test File | What It Covers |
|---|---|
| `test_config.py` | Config loading from YAML/JSON, structure validation, missing file handling |
| `test_dedup.py` | URL dedup, title SimHash dedup, content MinHash dedup, state export and restore |
| `test_bias.py` | MBFC database lookup, bias merge with and without framing data |
| `test_email_builder.py` | HTML email generation, article inclusion, subject line formatting |
| `test_extractor.py` | Paywall domain detection, text quality classification |
| `test_gemini_parse.py` | Fixture-based Gemini response parsing: JSON extraction, markdown stripping, grounding metadata |

### Fixtures

Tests use JSON/XML fixtures in `tests/fixtures/` rather than mocking API calls:
- `sample_articles.json` — representative article data for dedup and processing tests
- `sample_gemini_response.json` — captured Gemini Search response for parser testing
- `sample_rss.xml` — RSS feed sample for parser testing

Shared fixtures are loaded via `conftest.py` using pytest fixtures.

### Running Tests Locally

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=news_terminal --cov-report=term-missing

# Run a specific test file
pytest tests/test_dedup.py -v

# Run a specific test
pytest tests/test_gemini_parse.py::test_parse_json_response -v
```

### CI

Tests run automatically on every push to `main` and every pull request via `.github/workflows/test.yml`. The CI job installs `requirements-dev.txt` and runs `pytest tests/ -v --cov=news_terminal --cov-report=term-missing`.

---

## 11. Secrets Required

| Secret | Source | Required |
|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | **Yes** — powers search + processing |
| `RESEND_API_KEY` | [resend.com](https://resend.com) | Yes — email delivery |
| `GUARDIAN_API_KEY` | [open-platform.theguardian.com](https://open-platform.theguardian.com) | Optional — full-text articles |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions | Yes (auto) — gh-pages deploy |

Single Gemini account. No ToS violations.

---

## 12. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Gemini rate limits | Tiered models: Flash-Lite at 5s intervals (25% margin), Flash at 7s intervals (17% margin). Smart skip for pre-analyzed articles. 26% of daily budget used. Exponential backoff on 429s. |
| Gemini Search returns bad JSON | Two-phase parsing: strip markdown, find JSON array, regex fallback. If Phase 1 fails, Phase 2 extracts grounding URLs only. |
| Gemini Search API outage | Entire search block is in try/except. RSS collection still runs. Pipeline always produces output. |
| `response_schema` incompatible with `google_search` tool | Known API limitation. Search calls do NOT use response_schema — free-text response parsed manually. Documented in code and architecture. |
| RSS feed goes down | 28 sources — single failure is non-critical. Each feed in its own try/except. Weekly health check workflow. |
| Text extraction too slow | Capped at 100 articles max. Workflow timeout set to 25 minutes (was 20). |
| Sentence-transformers download slow | Model cached via `actions/cache@v4` (key: `st-all-MiniLM-L6-v2`). 80MB download only on first run or cache eviction. |
| GitHub Pages deploy kills archive | Uses `keep_files: true` (not `force_orphan`). Archive directory preserved between deploys. |
| Data branch grows | Monthly force-push cleanup. Only state.json persists (~50KB). |
| Bias detection inaccurate | Hybrid: MBFC database (authoritative) + LLM framing (labeled as AI-generated). |
| Concurrent workflow runs | `concurrency` group prevents overlap. |
| Search queries return poor results | Queries are in `config/search_queries.yaml` — editable without code changes. v1 queries, iterate based on output. |

---

## 13. Local Development

```bash
# Clone and setup
git clone https://github.com/yourusername/news_terminal.git
cd news_terminal
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for tests

# Set API key
export GEMINI_API_KEY="your-key-from-aistudio.google.com"

# Full pipeline (Gemini Search + RSS + Processing)
python run_local.py --slot morning

# RSS only (no Gemini Search, still does Gemini processing)
python run_local.py --slot morning --skip-search

# Collector test only (no Gemini at all)
python run_local.py --slot morning --skip-gemini --dry-run

# Preview site
cd site && python -m http.server 8080

# Run tests
pytest tests/ -v
```

---

## 14. What Changed: v3.0 to v3.1

This version addresses 12 specific review issues. All changes are reflected in code and documented here.

| # | Issue | Fix |
|---|---|---|
| 1 | `force_orphan: true` destroyed archive/ on every deploy | Switched to `keep_files: true`. Archive directory now persists between deploys. |
| 2 | "1M+ sources scanned" was misleading — we don't know what Google evaluates internally | Replaced with "Powered by Google Search + 28 direct feeds". Site shows actual grounding URL count. |
| 3 | Gemini Search output format was undocumented | Documented two-phase parsing: JSON from response text (no schema enforcement) + grounding_chunks from metadata. Known API limitation. |
| 4 | Text extraction timing tight for large runs | Capped at 100 articles max. Workflow timeout bumped 20 to 25 minutes. |
| 5 | Rate limit intervals had no safety margin | Flash-Lite: 5s (25% margin over 4s minimum). Flash: 7s (17% margin over 6s minimum). |
| 6 | sentence-transformers re-downloaded every run (80MB) | Added `actions/cache@v4` for `~/.cache/torch/sentence_transformers` with key `st-all-MiniLM-L6-v2`. |
| 7 | Dedup discarded articles instead of merging overlapping coverage | Merge strategy: sort by quality, upgrade text if better version found, preserve AI summaries, carry images across. |
| 8 | If Gemini Search failed, entire pipeline could fail | Search wrapped in try/except. Each supplementary source independently failable. RSS always runs. |
| 9 | Resend domain verification not documented | Added Prerequisites section with domain verification details. |
| 10 | No article images | RSS extracts from media:content/thumbnail/enclosure. Gemini prompt requests image_url. Card template shows 64x64 thumbnails. |
| 11 | Testing section was missing from architecture doc | Added section 10 documenting 37 tests across 6 files, fixtures, CI setup, and local run instructions. |
| 12 | Search queries were hardcoded in Python | Moved to `config/search_queries.yaml`. Loaded at runtime. Config change, not code change. |

---

## 15. Future Enhancements

| Phase | Feature | Effort |
|---|---|---|
| v3.2 | Telegram bot (instant CRITICAL alerts) | Low |
| v3.3 | Weekly trend analysis (Gemini-generated from week's data) | Medium |
| v3.4 | Cross-reference display (same event, N sources) | Low (cluster_id already built) |
| v3.5 | Source trust scoring (track accuracy over time) | Medium |
| v4.0 | Full-text search via Pagefind (static search) | Medium |
| v4.1 | Gemini agents for deep-dive research on CRITICAL stories | Medium |
| v4.2 | Voice briefing via Kokoro TTS | Medium |
| -- | Iterate search queries based on output quality | Ongoing |

---

*End of Architecture Document v3.1 — Implementation in progress.*
