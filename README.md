# Ecosystem Sanity Stack

An open-source framework for measuring media hygiene — extracting psychological signal from news flows using LLMs.

Deploy it for any news outlet in any country. Point it at your local news source, run it hourly, and watch the patterns emerge.

---

## What it does

The dashboard scores news articles on a single axis derived from four research-backed sub-scores:

| Dimension | Question | Direction |
|---|---|---|
| **Ragebait Index** | Is this emotion manufactured or authentic? | Higher = more manufactured (worse) |

The four sub-scores map directly to peer-reviewed clickbait detection frameworks:

| Sub-score | Research basis | What it detects |
|---|---|---|
| `curiosity_gap` | Blom & Hansen (2015) | Headline withholds information to force a click |
| `conflict_staging` | Rony et al. (2017) | Groups artificially pitted against each other |
| `emotional_inflation` | Potthast et al. (2016) | Emotional adjectives without factual backing |
| `narrative_exploitation` | Brady et al. (2017) | Moral outrage farming — villain/victim framing |

### Scoring pipeline

```
Tier 1 — Mistral Small    all new articles → pre_score (cheap, fast)
Tier 2 — Mistral Large    top candidates  → 4 parallel sub-scores → composite
Judge  — Mistral Large    compare top results → pick dashboard highlight
Reader Service            factual extract for the judge-selected article
```

---

## Theoretical foundation

### Why manufactured emotion is harmful

Three clinical studies form the wellbeing basis for why this measurement matters:

**McLaughlin, Gotlieb & Mills (2022)** — *Problematic News Consumption.* Health Communication.
Validated a clinical scale linking high-urgency news consumption directly to anxiety, depression, and sleep disturbance. Regular consumers of manufactured-emotion content enter a spiral where they must spend increasing energy to avoid consuming even more.

**McNaughton-Cassill & Smith (2002)** — *Optimism Gap.* Stress and Health.
News consumers systematically overestimate national threats relative to their lived experience. Emotional inflation and conflict staging feed this distortion, producing learned helplessness and irrational beliefs about the world.

**Crockett (2017)** — *Moral Outrage in the Digital Age.* Nature Human Behaviour.
Digital media reduce the cost of outrage expression (sharing, liking) to near zero. The result is habituation — outrage stimulus loses effect over time — plus moral licensing, where online outrage substitutes for real action. Manufactured outrage specifically depletes genuine moral capacity.

### Why the Ragebait Index measures what it claims to

**Blom & Hansen (2015)** coined "forward-reference" — headlines that reference content they deliberately withhold, forcing a click. Their empirical analysis of Danish news sites is the direct theoretical basis for `curiosity_gap`.

**Potthast et al. (2016)** built ML classifiers for clickbait and found the strongest predictor was the ratio of emotional adjectives (*skandalös*, *unglaublich*, *empörend*) to verifiable facts — the basis for `emotional_inflation`.

**Rony, Hassan & Yousuf (2017)** taxonomized clickbait patterns including "controversy manufacturing": articles whose sole purpose is to stage conflict between groups (*die Community ist gespalten*) to harvest comments — the basis for `conflict_staging`.

**Brady et al. (2017)** showed that moral-emotional language spreads significantly faster on social networks. This spread mechanism — villain/victim framing designed to trigger outrage and sharing — is what `narrative_exploitation` detects.

### Design decisions

- **Ragebait measures fabrication, not effect.** This distinguishes authentic heavy news (war, disaster — low ragebait, high emotional weight) from manufactured conflict over nothing (high ragebait, low actual weight).
- **The gate step** (Mistral Large qualitative check before full scoring) filters for genuine editorial inflation, so breaking news and hard factual reporting don't get scored alongside clickbait.
- **Temperature 0.0, seed 42** on all Tier-2 calls for reproducible results. Score version is stored with every article so you can re-score when prompts improve without losing history.

---

## Architecture

```
scheduler.py              ← fires pipeline at top of every hour
│
└── src/pipeline.py       ← core logic (importable by CLI and scheduler)
    │
    ├── Scrapers (4×)     ← 20min.ch · watson.ch · blick.ch · nau.ch
    ├── ArticleRepository ← upsert + SHA-256 content dedup
    ├── PreScorer         ← Mistral Small → pre_score (all new articles)
    ├── Gate              ← Mistral Large qualitative check (top candidates)
    ├── MediaScorer       ← Mistral Large → 4 parallel sub-scores (passed articles)
    └── Judge             ← Mistral Large → picks dashboard highlight
             │
             └── Streamlit dashboard  ← src/frontend/app.py
```

**Deduplication:** Every article is hashed (SHA-256 of title + content). Re-scraped unchanged articles only update `scraped_at` — no re-scoring. Changed content resets all scores.

**Rate limiting:** Thread-safe per-tier limiters (1 req/s for Large, 5 req/s for Small) prevent API bursts across parallel sub-score calls.

**Paywall filter:** Articles with `(B+)` in the title or fewer than 100 words are marked `pre_score=0` and skipped — scoring truncated marketing copy inflates every dimension artificially.

---

## Sources

Ships with four Swiss German news scrapers as reference implementations:

| Source | Connector | Method |
|---|---|---|
| [20min.ch](https://www.20min.ch) | `twenty_minutes_scraper_connector.py` | HTTP + JSON-LD |
| [watson.ch](https://www.watson.ch) | `watson_scraper_connector.py` | HTTP + JSON-LD |
| [blick.ch](https://www.blick.ch) | `blick_scraper_connector.py` | Playwright (bot-protected) |
| [nau.ch](https://www.nau.ch) | `nau_scraper_connector.py` | HTTP + JSON-LD |

All scrapers parse JSON-LD `NewsArticle` blocks with trafilatura as fallback.

---

## Local development

### Prerequisites

- Python 3.11+
- Docker Desktop
- [Mistral API key](https://console.mistral.ai/)

### 1. Clone & install

```bash
git clone https://github.com/Riddmaker/-Ecosystem-Sanity-Stack
cd -Ecosystem-Sanity-Stack
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
pip install -e . --no-deps     # makes `src` importable from anywhere (e.g. streamlit run)
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
MISTRAL_API_KEY=your_key_here
POSTGRES_USER=sanity
POSTGRES_PASSWORD=sanity
POSTGRES_DB=ecosystem_sanity
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql://sanity:sanity@localhost:5432/ecosystem_sanity
```

### 3. Start everything

```bash
docker compose up -d
```

Starts three containers: `db` (PostgreSQL 16), `frontend` (Streamlit on port 8501), `scheduler` (hourly pipeline).

Open [http://localhost:8501](http://localhost:8501).

### Run the pipeline manually

```bash
# One-shot via Docker (recommended — includes Playwright for Blick):
docker compose run --rm worker python run_pipeline.py --hours 1

# Or directly via venv (requires local PostgreSQL):
python run_pipeline.py --hours 3 --max-articles 10 --sources 20min watson
```

Available flags:

| Flag | Description |
|---|---|
| `--hours N` | Only include articles published in the last N hours |
| `--max-articles N` | Cap per source (useful for testing) |
| `--sources` | Space-separated list: `20min watson blick nau` |

---

## Testing

### Unit tests — no network, no DB required

```bash
pytest tests/test_connectors.py -v
```

Covers all four scrapers and the base class utilities (50+ tests): link extraction, article ID parsing, breadcrumb parsing, full article parsing with HTML fixtures.

### Integration tests — requires live DB and/or API key

Make sure `.env` is configured and the database is running (`docker compose up -d db`).

```bash
# Scraper integration — requires DB
pytest tests/test_integration_scraper.py -m integration -v

# Scoring integration — requires MISTRAL_API_KEY
pytest tests/test_integration_scoring.py -m integration -v

# All integration tests
pytest tests/ -m integration -v
```

What the integration tests verify:

**Scraper (`test_integration_scraper.py`):**
- Fetches real articles from 20min.ch
- Upserts to DB and confirms records are created
- Re-upserting same articles marks them as unchanged (dedup works)
- All required fields are populated

**Scoring (`test_integration_scoring.py`):**
- `PreScorer` returns a score in [0, 10] with reasoning
- Factual articles score below 6, clickbait scores above 5
- `MediaScorer` returns all four sub-scores in range
- `ragebait_score` is the mean of the four sub-scores (within tolerance)
- `gate_article()` returns a `pass` boolean + reasoning
- `judge_articles()` picks a valid winner from a candidate list

### Run all tests

```bash
pytest tests/ -v                    # unit tests only (fast, no external deps)
pytest tests/ -m integration -v    # integration tests only
pytest tests/ -v --tb=short        # all tests with compact tracebacks
```

---

## Production deployment on Jelastic (Infomaniak)

The app runs as a **single Docker container** on Jelastic PaaS (hosted by Infomaniak at `jcloud.ik-server.com`), with a separate managed PostgreSQL node. `start.sh` starts the scheduler in the background and Streamlit in the foreground in the same container.

### How the CI/CD flow works

```
Push / merge to main
        │
        ▼
GitHub Actions (.github/workflows/deploy-prod.yml)
  1. Build Docker image
  2. Push to ghcr.io/riddmaker/ecosystem-sanity-stack:latest
  3. Fire JELASTIC_WEBHOOK_PROD
        │
        ▼
Jelastic pulls :latest → redeploys the container
```

### First-time Jelastic setup

**1. Create the environment in Jelastic**

In the Infomaniak Jelastic console, create a new environment:
- Add a **Docker** application server node — use the image `ghcr.io/riddmaker/ecosystem-sanity-stack:latest`
- Add a **PostgreSQL 16** database node

**2. Make the GHCR package public**

Go to `github.com/Riddmaker` → Packages → `ecosystem-sanity-stack` → Package Settings → Change visibility to **Public**.

Otherwise Jelastic cannot pull the image without registry credentials.

**3. Set environment variables on the application server node**

In the Jelastic console, open the application server node → Variables, and add:

```
MISTRAL_API_KEY=your_mistral_api_key
DATABASE_URL=postgresql://<pg-user>:<pg-password>@<pg-node-hostname>:5432/<db-name>
POSTGRES_HOST=<internal pg node hostname>
POSTGRES_USER=<pg user>
POSTGRES_PASSWORD=<pg password>
POSTGRES_DB=<db name>
POSTGRES_PORT=5432
```

The PostgreSQL hostname, user, and password are shown in the Jelastic DB node details panel.

**4. Open port 8501**

In the Jelastic environment → Endpoints or Public IP settings, map external traffic to internal port `8501` (Streamlit).

**5. Add the webhook secret to GitHub**

In the Jelastic environment settings, find the **Auto-deploy webhook URL**. Copy it and add it to GitHub:

Repository → Settings → Secrets and variables → Actions → New secret:

| Secret | Value |
|---|---|
| `JELASTIC_WEBHOOK_PROD` | Your Jelastic auto-redeploy webhook URL |

### Deploying

After the first-time setup, deployment is automatic:

```bash
git push origin main   # triggers GitHub Actions → builds image → Jelastic redeploys
```

To trigger a redeploy without a code change (e.g. to apply new Jelastic env vars):

In GitHub → Actions → `Deploy to Production (main)` → `Run workflow`.

### Initial data warm-up

On first deploy the scheduler immediately runs with a 1.5-hour lookback. If you want a fuller dataset on day one, trigger a manual backfill via the worker:

```bash
# From your local machine (with Docker running):
docker compose run --rm worker python run_pipeline.py --hours 24
```

Then push the data to the production DB, or just let the scheduler fill it naturally over the first day.

---

## Adapting to your news source

### Option A — Build a scraper connector

Create a file in `src/connectors/specific_scraper/` implementing `BaseScraperConnector`:

```python
from src.connectors.abstract.scraper_connector import BaseScraperConnector
from src.connectors.abstract.models import Article

class MyNewsConnector(BaseScraperConnector):
    SOURCE = "mynews.com"
    LANGUAGE = "en"

    @property
    def index_urls(self) -> list[str]:
        return ["https://mynews.com/", "https://mynews.com/politics/"]

    def extract_article_links(self, html: str, base_url: str) -> list[str]:
        # Return list of article URLs found on the index page
        ...

    def parse_article(self, url: str, html: str) -> Article | None:
        # Parse a single article page, return Article or None
        ...

    def _extract_article_id(self, url: str) -> str | None:
        # Return a stable unique ID for this article (for dedup)
        ...
```

Then add it to `src/pipeline.py` alongside the existing sources.

### Option B — RSS feed connector

Use `BaseRSSConnector` in `src/connectors/abstract/rss_connector.py` for sources that expose an RSS feed.

### The Article model

```python
Article(
    title="...",
    url="...",
    content="...",            # full article text
    source="mynews.com",
    source_article_id="123",  # stable ID from the source (for dedup)
    language="en",
    published_at=datetime(..., tzinfo=timezone.utc),
    # optional:
    author="...",
    category="...",
    tags=["tag1", "tag2"],
    summary="...",
    word_count=450,
)
```

---

## Project structure

```
ecosystem-sanity-stack/
├── run_pipeline.py              # CLI entry point (one-shot run)
├── scheduler.py                 # hourly loop — calls src/pipeline.py
├── start.sh                     # container entrypoint: scheduler + frontend
├── pytest.ini                   # test configuration
├── pyproject.toml               # packaging — `pip install -e .` makes src importable
├── src/
│   ├── pipeline.py              # core pipeline logic (importable)
│   ├── config.py                # cross-cutting tunables (thresholds, windows)
│   ├── connectors/
│   │   ├── abstract/            # BaseScraperConnector, RSSConnector, Article model
│   │   └── specific_scraper/    # 20min · watson · blick · nau
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM (ArticleModel)
│   │   ├── repository.py        # upsert, dedup, query helpers
│   │   └── connection.py        # engine + session factory
│   ├── scoring/
│   │   ├── llm_client.py        # shared Mistral JSON client (retry, rate limits)
│   │   ├── pre_scorer.py        # Tier-1: Mistral Small
│   │   ├── pre_prompts.py       # Tier-1 prompt
│   │   ├── scorer.py            # Tier-2 + judge: Mistral Large
│   │   ├── prompts.py           # Tier-2 prompts (German, few-shot)
│   │   ├── schemas.py           # Pydantic schemas
│   │   └── throttle.py          # rate limiter singletons
│   └── frontend/
│       ├── app.py               # Streamlit dashboard (composition)
│       ├── data.py              # DB queries + highlight selection
│       ├── components.py        # HTML builders for the dashboard cards
│       └── styles.py            # CSS + theming
├── tests/
│   ├── conftest.py              # shared fixtures + skip conditions
│   ├── test_connectors.py       # unit tests — all 4 scrapers (no network/DB)
│   ├── test_integration_scraper.py   # integration — scrape + DB upsert
│   └── test_integration_scoring.py  # integration — pre-score + full score
├── migrations/
│   ├── migrate_v3_to_v4.py
│   └── migrate_v4_to_v5.py
├── Dockerfile
├── docker-compose.yml           # local dev: db + frontend + scheduler + worker
├── docker-compose.prod.yml      # production overrides (VPS deployment)
└── requirements.txt
```

---

## Score versioning

Each article stores `score_version` and `score_model` so you can re-score when prompts improve without losing history.

| Version | Change |
|---|---|
| `v9` | Current — narrative_exploitation added as 4th sub-score, 4 parallel Large calls |
| `v6-pre` | Current pre-screen — Mistral Small, 250-word snippet |
| `v7` | Added narrative_exploitation, per-sub-score reasoning fields |
| `v4` | Original — Ragebait Index + Emotional Weight (2-axis) |

---

## Database migrations

| Script | Changes |
|---|---|
| `migrate_v3_to_v4.py` | Renamed `sanity_score` → `ragebait_score`, added `emotional_weight` |
| `migrate_v4_to_v5.py` | Added pre-score columns (Tier-1 screening) |

Run with:
```bash
python migrations/migrate_vX_to_vY.py
```

---

## References

| Paper | DOI |
|---|---|
| Blom & Hansen (2015) — Click bait: Forward-reference as lure | [10.1080/17512786.2014.976939](https://doi.org/10.1080/17512786.2014.976939) |
| Potthast et al. (2016) — Clickbait Detection | [10.1007/978-3-319-30671-1_72](https://doi.org/10.1007/978-3-319-30671-1_72) |
| Rony, Hassan & Yousuf (2017) — Diving Deep into Clickbaits | [10.1145/3091478.3091487](https://doi.org/10.1145/3091478.3091487) |
| Brady et al. (2017) — Emotion shapes the diffusion of moralized content | [10.1073/pnas.1618923114](https://doi.org/10.1073/pnas.1618923114) |
| McLaughlin, Gotlieb & Mills (2022) — Problematic News Consumption | [10.1080/10410236.2022.2106086](https://doi.org/10.1080/10410236.2022.2106086) |
| McNaughton-Cassill & Smith (2002) — Optimism Gap | [10.1002/smi.916](https://doi.org/10.1002/smi.916) |
| Crockett (2017) — Moral Outrage in the Digital Age | [10.1038/s41562-017-0213-3](https://doi.org/10.1038/s41562-017-0213-3) |
