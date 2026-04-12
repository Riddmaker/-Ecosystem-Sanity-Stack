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

### Two-tier cost model

Scoring every article with a large LLM would be expensive. Instead:

1. **Tier 1 — Mistral Small** screens all new articles (title + first 500 chars). Cheap. Fast. Runs on every article per scrape batch.
2. **Tier 2 — Mistral Large** runs the full analysis (both dimensions, all sub-scores) only on the article with the highest Tier-1 flag. That article becomes the dashboard highlight.

The dashboard shows: *"Our small model flagged X of Y articles in the last batch. Strongest signal in detail."*

---

## Architecture

```
run_pipeline.py          ← hourly entry point
│
├── Scraper              ← pulls articles from your news source
├── ArticleRepository    ← upsert with SHA-256 content dedup
├── PreScorer            ← Mistral Small, title + 500 chars → pre_score
└── MediaScorer          ← Mistral Large, full content → ragebait + weight
         │
         └── Streamlit dashboard  ← src/frontend/app.py
```

**Deduplication:** Every article is hashed (SHA-256 of content). Re-scraped unchanged articles only update `scraped_at` — no re-scoring. Changed content resets all scores.

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

## Setup

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL)
- [Mistral API key](https://console.mistral.ai/)

### 1. Clone & install

```bash
git clone https://github.com/your-org/ecosystem-sanity-stack
cd ecosystem-sanity-stack
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
DATABASE_URL=postgresql://sanity:sanity@localhost:5432/sanity
```

### 3. Start the database

```bash
docker-compose up -d
```

### 4. Run the pipeline (first time)

```bash
python run_pipeline.py
```

This will:
- Scrape your configured news source
- Pre-screen all articles with Mistral Small
- Full-analyze the top flagged article with Mistral Large

### 5. Start the dashboard

```bash
.venv/Scripts/python -m streamlit run src/frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501).

### 6. Schedule hourly runs

**Linux/macOS (cron):**
```bash
crontab -e
# Add:
0 * * * * /path/to/.venv/bin/python /path/to/run_pipeline.py >> /var/log/sanity.log 2>&1
```

**Windows (Task Scheduler):**
Create a Basic Task → Trigger: Daily, repeat every 1 hour → Action: `.venv\Scripts\python.exe run_pipeline.py`

---

## Adapting to your news source

The project ships with a scraper for [20min.ch](https://www.20min.ch) (Switzerland) as a reference implementation. To use it with your local news source:

### Option A — Build a scraper connector

Create a new file in `src/connectors/specific_scraper/` implementing `BaseScraperConnector`:

```python
from src.connectors.abstract.scraper_connector import BaseScraperConnector
from src.connectors.abstract.models import Article

class MyNewsConnector(BaseScraperConnector):
    SOURCE = "mynews.com"
    LANGUAGE = "en"

    def get_articles(self, max_articles=None, **kwargs) -> list[Article]:
        # Your scraping logic here
        # Return a list of Article objects
        ...
```

Then update `run_pipeline.py` to use your connector:

```python
from src.connectors.specific_scraper.my_news_connector import MyNewsConnector
connector = MyNewsConnector()
```

### Option B — RSS feed connector

An `RSSConnector` base class is available in `src/connectors/abstract/rss_connector.py` for sources that expose an RSS feed.

### The Article model

Your connector needs to return `Article` objects (defined in `src/connectors/abstract/models.py`):

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

## Database migrations

| Script | Changes |
|---|---|
| `migrate_v3_to_v4.py` | Renamed sanity_score → ragebait_score, added emotional_weight |
| `migrate_v4_to_v5.py` | Added pre_score columns (Tier-1 screening) |

Run with: `.venv/Scripts/python migrate_vX_to_vY.py`

---

## Project structure

```
ecosystem-sanity-stack/
├── run_pipeline.py              # hourly entry point: scrape → pre-screen → full-score
├── src/
│   ├── connectors/
│   │   ├── abstract/            # BaseScraperConnector, RSSConnector, Article model
│   │   └── specific_scraper/    # 20min.ch reference implementation
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM (ArticleModel)
│   │   ├── repository.py        # upsert, dedup, get_unscored helpers
│   │   └── connection.py        # engine + session factory
│   ├── scoring/
│   │   ├── pre_scorer.py        # Tier-1: Mistral Small
│   │   ├── pre_prompts.py       # Tier-1 prompt
│   │   ├── scorer.py            # Tier-2: Mistral Large (MediaScorer)
│   │   ├── prompts.py           # Tier-2 prompts (German, few-shot)
│   │   └── schemas.py           # Pydantic schemas
│   └── frontend/
│       └── app.py               # Streamlit dashboard
├── THEORETICAL_FOUNDATION.md    # Research context
├── docker-compose.yml           # PostgreSQL
└── requirements.txt
```

---

## Score versioning

Each article stores `score_version` and `score_model` so you can re-score when prompts improve without losing history.

Current version: **v4** (Ragebait Index + Emotional Weight, Mistral Large Latest, temp=0.0, seed=42)
Pre-screen version: **v4-pre** (Mistral Small Latest)

---
