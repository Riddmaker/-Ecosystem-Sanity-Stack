# Ecosystem Sanity Stack

An open-source framework for measuring media hygiene — extracting psychological signal from news flows using LLMs.

Deploy it for any news outlet in any country. Point it at your local news source, run it hourly, and watch the patterns emerge.

---

## What it does

The dashboard scores news articles on two independent axes:

| Dimension | Question | Direction |
|---|---|---|
| **Ragebait Index** | Is this emotion manufactured or authentic? | Higher = more manufactured (worse) |
| **Emotional Weight** | How heavy is this content to process? | Neutral descriptor — no judgment |

Reading them together tells the real story:

- **Low ragebait + High weight** → Authentic hard news (war, disaster). Legitimate — but take breaks.
- **High ragebait + Low weight** → Pure clickbait. Manufactured conflict over nothing.
- **High ragebait + High weight** → Worst pattern: exploitation of real suffering for engagement.
- **Low ragebait + Low weight** → Clean informational content.

### Two-tier cost model + judge

Scoring every article with a large LLM would be expensive. Instead:

1. **Tier 1 — Mistral Small** screens all new articles (title + first 500 chars). Cheap. Fast. Runs on every article per batch.
2. **Tier 2 — Mistral Large** runs the full analysis (both dimensions, all sub-scores) on the top 5 flagged candidates.
3. **Judge step — Mistral Large** compares the top 5 results qualitatively and picks the dashboard highlight, with reasoning.

---

## Architecture

```
scheduler.py             ← runs pipeline hourly
│
└── src/pipeline.py      ← core pipeline logic
    │
    ├── Scrapers (4x)    ← 20min.ch · watson.ch · blick.ch · nau.ch
    ├── ArticleRepository← upsert with SHA-256 content dedup
    ├── PreScorer        ← Mistral Small → pre_score (all new articles)
    ├── MediaScorer      ← Mistral Large → ragebait + emotional weight (top 5)
    └── Judge            ← Mistral Large → picks dashboard highlight from top 5
             │
             └── Streamlit dashboard  ← src/frontend/app.py
```

**Deduplication:** Every article is hashed (SHA-256 of content). Re-scraped unchanged articles only update `scraped_at` — no re-scoring. Changed content resets all scores.

**Rate limiting:** Thread-safe per-tier limiters (1 req/s for Large, 5 req/s for Small) prevent API bursts across parallel calls.

---

## Sources

Ships with four Swiss German news scrapers as reference implementations:

| Source | Connector |
|---|---|
| [20min.ch](https://www.20min.ch) | `twenty_minutes_scraper_connector.py` |
| [watson.ch](https://www.watson.ch) | `watson_scraper_connector.py` |
| [blick.ch](https://www.blick.ch) | `blick_scraper_connector.py` |
| [nau.ch](https://www.nau.ch) | `nau_scraper_connector.py` |

All four scrapers parse JSON-LD `NewsArticle` blocks with trafilatura as fallback.

---

## Research foundation

### Ragebait Index — Clickbait Detection Research

- **Blom & Hansen (2015)** — *Click bait: Forward-reference as lure in online news headlines.* Journalism Practice. → `curiosity_gap` sub-score
- **Potthast et al. (2016)** — *Clickbait Detection.* ECIR. → `emotional_inflation` sub-score
- **Rony, Hassan & Yousuf (2017)** — *Diving Deep into Clickbaits.* ACM WebSci. → `conflict_staging` sub-score

### Why manufactured emotion is harmful — Wellbeing Research

- **McLaughlin, Gotlieb & Mills (2022)** — *Problematic News Consumption.* Health Communication.
- **McNaughton-Cassill & Smith (2002)** — *Optimism Gap.* Stress and Health.
- **Crockett (2017)** — *Moral Outrage in the Digital Age.* Nature Human Behaviour.

See [`THEORETICAL_FOUNDATION.md`](THEORETICAL_FOUNDATION.md) for the full theoretical context.

---

## Local development

### Prerequisites

- Python 3.11+
- Docker
- [Mistral API key](https://console.mistral.ai/)

### 1. Clone & install

```bash
git clone https://github.com/Riddmaker/-Ecosystem-Sanity-Stack
cd -Ecosystem-Sanity-Stack
python -m venv .venv
.venv/Scripts/activate       # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env`:

```
MISTRAL_API_KEY=your_key_here
POSTGRES_USER=sanity
POSTGRES_PASSWORD=sanity
POSTGRES_DB=sanity
POSTGRES_PORT=5432
DATABASE_URL=postgresql://sanity:sanity@localhost:5432/sanity
```

### 3. Start everything

```bash
docker compose up -d
```

This starts three containers: `db` (PostgreSQL), `frontend` (Streamlit on port 8501), `scheduler` (hourly pipeline runner).

Open [http://localhost:8501](http://localhost:8501).

### Run the pipeline manually

```bash
python run_pipeline.py
# or with filters:
python run_pipeline.py --hours 3 --max-articles 10 --sources 20min watson
```

---

## Production deployment

The app runs as a **single Docker container** on [Jelastic PaaS](https://jelastic.com/), with a separate managed PostgreSQL node.

The container runs `start.sh` which starts the scheduler in the background and Streamlit in the foreground.

### Deployment flow

```
Push / merge to main
        │
        ▼
GitHub Actions (deploy-prod.yml)
  → Build image
  → Push ghcr.io/riddmaker/ecosystem-sanity-stack:latest
  → Fire JELASTIC_WEBHOOK_PROD
        │
        ▼
Jelastic pulls :latest and redeploys
```

### Required GitHub secrets

| Secret | Value |
|---|---|
| `JELASTIC_WEBHOOK_PROD` | Redeploy webhook URL from your Jelastic environment |

### Required environment variables in Jelastic

```
MISTRAL_API_KEY=...
DATABASE_URL=postgresql://user:password@<db-host>/dbname
POSTGRES_HOST=<internal db hostname>
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_PORT=5432
```

---

## Adapting to your news source

### Option A — Build a scraper connector

Create a new file in `src/connectors/specific_scraper/` implementing `BaseScraperConnector`:

```python
from src.connectors.abstract.scraper_connector import BaseScraperConnector
from src.connectors.abstract.models import Article

class MyNewsConnector(BaseScraperConnector):
    SOURCE = "mynews.com"
    LANGUAGE = "en"

    def get_articles(self, since=None, max_articles=None) -> list[Article]:
        # Your scraping logic here
        ...
```

Then add it to `src/pipeline.py` alongside the existing sources.

### Option B — RSS feed connector

An `RSSConnector` base class is available in `src/connectors/abstract/rss_connector.py` for sources that expose an RSS feed.

### The Article model

```python
Article(
    title="...",
    url="...",
    content="...",           # full article text
    source="mynews.com",
    source_article_id="123", # unique ID from the source (for dedup)
    language="en",
    published_at=datetime(...),
    # optional: author, category, tags, summary, word_count
)
```

---

## Project structure

```
ecosystem-sanity-stack/
├── run_pipeline.py              # CLI entry point (one-shot run)
├── scheduler.py                 # hourly loop — calls src/pipeline.py
├── start.sh                     # container entrypoint: scheduler + frontend
├── src/
│   ├── pipeline.py              # core pipeline logic (importable)
│   ├── connectors/
│   │   ├── abstract/            # BaseScraperConnector, RSSConnector, Article model
│   │   └── specific_scraper/    # 20min · watson · blick · nau
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM (ArticleModel)
│   │   ├── repository.py        # upsert, dedup, query helpers
│   │   └── connection.py        # engine + session factory
│   ├── scoring/
│   │   ├── pre_scorer.py        # Tier-1: Mistral Small
│   │   ├── pre_prompts.py       # Tier-1 prompt
│   │   ├── scorer.py            # Tier-2 + judge: Mistral Large
│   │   ├── prompts.py           # Tier-2 prompts (German, few-shot)
│   │   ├── schemas.py           # Pydantic schemas
│   │   └── throttle.py          # rate limiter singletons
│   └── frontend/
│       └── app.py               # Streamlit dashboard
├── tests/
│   └── test_connectors.py       # unit tests for all 4 scrapers (no network/DB)
├── migrations/
│   ├── migrate_v3_to_v4.py
│   └── migrate_v4_to_v5.py
├── Dockerfile
├── docker-compose.yml           # local dev: db + frontend + scheduler
├── THEORETICAL_FOUNDATION.md
└── requirements.txt
```

---

## Score versioning

Each article stores `score_version` and `score_model` so you can re-score when prompts improve without losing history.

Current version: **v4** (Ragebait Index + Emotional Weight, Mistral Large Latest, temp=0.0, seed=42)
Pre-screen version: **v4-pre** (Mistral Small Latest)

---

## Database migrations

| Script | Changes |
|---|---|
| `migrate_v3_to_v4.py` | Renamed sanity_score → ragebait_score, added emotional_weight |
| `migrate_v4_to_v5.py` | Added pre_score columns (Tier-1 screening) |

Run with: `.venv/Scripts/python migrations/migrate_vX_to_vY.py`
