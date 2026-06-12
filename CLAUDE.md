# CLAUDE.md

Guidance for AI agents (Claude Code) working in this repository. See `README.md` for
the full project description, research basis, and deployment guide.

## What this is
Ecosystem Sanity Stack — measures "media hygiene" by scoring Swiss German news articles
for manufactured emotion (a **Ragebait Index**) using a two-tier Mistral LLM pipeline,
surfaced on a Streamlit dashboard.

**Stack:** Python 3.11 · PostgreSQL (SQLAlchemy) · Mistral API (Small + Large) ·
Streamlit · Docker · deployed to Jelastic (Infomaniak) via GitHub Actions.

## Setup
```bash
python -m venv .venv && .venv/Scripts/activate   # Windows; on *nix: source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-deps                        # makes `src` importable (no sys.path hacks)
```
Secrets live in a gitignored `.env` (copy from `.env.example`). **Never commit real
secrets, and never copy real values into the `.example` files** — keep placeholders there.

## Common commands
```bash
# Tests
pytest -m "not integration"     # unit tests — fast, no DB/API needed
pytest -m integration           # integration — needs a running DB and MISTRAL_API_KEY
pytest                          # everything

# Pipeline
python run_pipeline.py --hours 2 --max-articles 5 --sources 20min
docker compose run --rm worker python run_pipeline.py --hours 1   # via Docker (incl. Playwright)

# Dashboard / local stack
streamlit run src/frontend/app.py
docker compose up -d            # db + frontend + scheduler
```

## Architecture (where things live)
- `src/pipeline.py` — orchestration. `run()` composes `_scrape → _prescreen → _gate →
  _full_score → _pick_winner`. Sources are a `CONNECTORS` registry; add new sources there.
- `src/config.py` — all cross-cutting tunables (gate threshold, candidate limit, paywall
  marker, word minimums, scheduler lookback). **Put magic numbers here, not inline.**
- `src/connectors/abstract/scraper_connector.py` — `BaseScraperConnector` owns ONE shared
  crawl loop (template method). Concrete scrapers declare class attrs
  (`SOURCE`/`BASE_URL`/`DEFAULT_SECTIONS`/`CRAWL_DELAY`) and implement
  `extract_article_links`, `parse_article(html, url)`, `_extract_article_id`.
  Bot-protected sites extend `BasePlaywrightScraperConnector`.
- `src/scoring/llm_client.py` — shared `MistralJSONClient` (key handling, JSON mode,
  temp=0.0/seed=42, rate limiting, 429 retry). `PreScorer`/`MediaScorer` are thin wrappers.
- `src/db/` — `connection.py` (engine singleton + `init_db()`), `models.py` (ORM),
  `repository.py` (upsert + SHA-256 content dedup + query helpers).
- `src/frontend/` — `app.py` (composition) · `data.py` (queries) · `components.py`
  (HTML builders) · `styles.py` (CSS/themes).
- `scheduler.py` / `run_pipeline.py` — hourly daemon / one-shot CLI; both import `pipeline.run`.

## Conventions
- Use the `logging` module (`log = logging.getLogger(__name__)`), not `print`.
- Keep tunables in `src/config.py`.
- Tier-2 scoring is deterministic: temperature 0.0 + seed 42.
- Rate limits live in `src/scoring/throttle.py` (Large ~1 req/s, Small ~5 req/s). Live
  runs will hit 429s and back off — that's expected, not a bug.
- Integration tests skip cleanly without a DB / `MISTRAL_API_KEY`.

## Git & deployment workflow
- `main` is **protected** — no direct pushes. Work on `dev` or a feature branch, push,
  open a PR; the maintainer merges.
- Merging to `main` triggers `.github/workflows/deploy-prod.yml`: build image → push to
  `ghcr.io/riddmaker/ecosystem-sanity-stack:latest` → fire the `JELASTIC_WEBHOOK_PROD`
  secret → Jelastic re-pulls and redeploys. **Every merge to `main` is a production deploy.**

## Gotchas
- Windows dev environment (PowerShell + Git Bash). Use the `.venv` Python, not system Python.
- Paywalled/teaser articles (`(b+)` in title or fewer than `MIN_ARTICLE_WORDS` words) are
  marked `pre_score=0` and skipped — scoring truncated marketing copy inflates every metric.
- `_parse_datetime` falls back to `now()` for missing/unparseable dates, which affects the
  `since` filter (intentional — left as-is).
