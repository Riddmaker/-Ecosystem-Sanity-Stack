# CLAUDE.md

Guidance for AI agents (Claude Code) working in this repository. See `README.md` for
the full project description, research basis, and deployment guide.

<coding_conventions>
- HABIT 1: [Security First] Never hardcode sensitive credentials or API keys; always use environment variables. Actively avoid reading, echoing, or printing raw secret values into the terminal or chat context to prevent them from leaking into the LLM context window.
- HABIT 2: [Agentic Initiative] When fixing errors, analyze the terminal output directly using CLI commands rather than asking the user to copy-paste logs.
- HABIT 3: [Plan First] Before executing any complex task, you must draft a clear, step-by-step execution plan based on existing documentation. Lay it out for yourself and the user, and wait for explicit approval before writing code.
- HABIT 4: [Library Integrity] When working with external libraries, never guess the syntax. You must first consult the official documentation or the local source code (via the venv or internet tools) to ensure the library, with the version we use in the code-bse, is applied correctly semantically and synthactically.
- HABIT 5: [Documentation & Context Maintenance] Keep the repository's documentation, template files (like .env.example or config.sample.json), and AI context files (like claude.md or memory logs) up-to-date with code changes. Ensure AI memory and instruction files are maintained where necessary and appropriate for their specific purposes. Ensure example configurations always reflect the actual required keys and structure of the working environment without ever containing real secrets. Ensure zero contradictions between the code, docs, and AI context. If contradictions arise, highlight them, decide on the best path, or discuss them with the user.
- HABIT 6: [Step-by-Step Reasoning] Before performing any architectural change or fix, layout a logical reasoning process. Think through edge cases step-by-step before executing commands.
- HABIT 7: [Meta-Optimization] Continuously evaluate our interactions. If you notice repetitive manual tasks, recurring boilerplate generation, or identical shell commands being executed across multiple turns, STOP and proactively suggest an automation. Advise the user if creating a new Skill, Hook, or Plugin from the Marketplace, or using a dedicated CLI or MCP, or using a Subagent would optimize the workflow, strictly following the "Lightest First" philosophy.
- HABIT 8: [Standardized Quality] Always write code that adheres to established, language-specific style guides (e.g., PEP 8 for Python). Anticipate and prevent the warnings, errors, and hints that standard static analysis tools and linters (like Pylint or ESLint) would flag. Treat clean, idiomatic, and internally consistent syntax as a strict requirement, not an afterthought.
- HABIT 9: [Secure by Design] Actively integrate fundamental cybersecurity principles into every layer of the application. Validate all inputs, sanitize outputs, and specifically guard against the OWASP Top 10 vulnerabilities (such as SQL Injection, Cross-Site Scripting (XSS), and Broken Access Control). Always apply the principle of least privilege when configuring permissions, databases, or APIs.
- HABIT 10: [Verifiable Reliability] Ensure the application remains fully testable. For any significant new functionality, write corresponding automated tests and place them in a dedicated tests/ directory at the project root. Before any code is considered "complete" or ready for deployment, run the relevant test suites to verify that the new features work and that no existing functionality has been broken.
</coding_conventions>

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
docker compose run --rm worker python run_pipeline.py --hours 1   # via Docker (one-shot)

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
- `scheduler.py` / `run_pipeline.py` — hourly daemon / one-shot CLI. The daemon runs the
  pipeline immediately on startup, then at the top of every hour (`:00`), each cycle as a
  **subprocess** (`run_pipeline.py`) that exits so its memory peak is reclaimed between runs
  (an in-process run left ~280 MiB resident at idle). `run_pipeline.py` imports `pipeline.run`.

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
- **Blick is disabled in production** (`config.DISABLED_SOURCES`). Akamai bot protection
  returns `403` to datacenter IP ranges (Infomaniak/Jelastic) for the *entire* `blick.ch`
  domain — pages, sitemaps and RSS — so it can't be scraped from the server. It still works
  from a residential IP, so it stays in `CONNECTORS` and can be run explicitly
  (`run_pipeline.py --sources blick`) locally. A default run scrapes `DEFAULT_SOURCES` only.
- **The Docker image no longer ships Playwright/Chromium** (dropped to slim the prod image;
  Blick is prod-disabled anyway). Playwright is imported lazily, so the pipeline runs fine
  without it. To scrape Blick locally, install it first: `pip install playwright &&
  playwright install chromium`. `requirements.txt` no longer lists `playwright`.
- `_scrape` runs each source under a hard wall-clock cap (`config.SCRAPE_SOURCE_TIMEOUT`).
  A connector that hangs (e.g. a Playwright navigation that ignores its own timeout against
  a bot wall) is abandoned so it can never freeze the whole run / the hourly daemon.
- **The dashboard serves on port `8080`, not 8501** (`start.sh`). Jelastic routes the
  environment URL to `JELASTIC_PRIORITY_PORTS=8080`; serving anywhere else = "connection
  refused" on the public URL. `docker-compose` maps host `8501` → container `8080`, so
  `http://localhost:8501` still works in local dev.
- **Cloudflare Tunnel is opt-in via `TUNNEL_TOKEN`** (`start.sh`). The image ships the
  `cloudflared` binary; `start.sh` only launches the tunnel when `TUNNEL_TOKEN` is set
  (prod env var), otherwise it's a no-op (local dev / docker-compose are unaffected). The
  tunnel is outbound-only and maps its public hostname → `http://localhost:8080` in the
  Cloudflare Zero Trust dashboard, so the prod env serves the public URL **without a public
  IP**. Token is set on the cp node, never committed.

## Fact-Check track (Irreführungs-Index) — BUILT, off by default
A **second scoring track** in `src/factcheck/`, surfaced as the **Faktencheck** dashboard tab
alongside the Ragebait Index, reusing the **same scraped articles** (scrape once, two tracks).
Gated behind `config.FACTCHECK_ENABLED` (default `False`) — while off, the ragebait pipeline and
local dev are byte-for-byte unchanged. Open-book flow:
- **Pre-flag** suspicion of unverified/unchecked claims (Mistral Small) — `pre_flag.py`, stage 3b.
- **Winner-only** (cost control): a judge picks the single best of the top-5 suspicious, and only
  that article gets claim extraction (`claims.py`) + Tavily web retrieval — `_fc_factcheck` in
  `pipeline.py`, throttled by `FACTCHECK_EVERY_N_RUNS` via the stateless `_factcheck_due` gate.
- **Evidence:** Google Fact Check Tools API (free, 1st pass) then Tavily fallback — `retrieval.py`;
  **both guard on a missing key → `[]`**, so the ragebait track / local dev are never blocked.
- **3 Mistral-Large sub-scores, one call each** — `scorer.py`: Factual Accuracy (open-book, FEVER
  SUPPORTED/REFUTED/**NEI**) / Misleading Framing (Entman) / Missing Context (Rogers). Mean =
  `fact_check_score`. **NEI is excluded from the mean** so abstention never inflates the index;
  never assert "lie" about a named outlet.
- Frontend (`src/frontend/`): `st.tabs(["Ragebait Index","Faktencheck"])` + a "Was du sonst tun
  kannst" shout-out to the **Pino** fact-check extension. Config knobs in `config.py`
  (`FACTCHECK_*`), retrieval keys `GOOGLE_FACTCHECK_API_KEY` / `TAVILY_API_KEY` in `.env`.

Full design, phase history and study anchors live in agent memory (`project-factcheck-plan`).
- **DB gotcha:** `create_all()` does NOT ALTER existing tables — the fact-check columns are added
  by an idempotent `ADD COLUMN IF NOT EXISTS` migration in `db/connection.py::run_migrations()`
  (Postgres-only, wired into `init_db()`), not by the model change alone.
- **Enabling = prod cost + a public verdict:** flip `FACTCHECK_ENABLED=True` only with both
  retrieval keys set on the target env; every merge to `main` is a production deploy.
