# Ecosystem Sanity Stack

An open-source framework for measuring media hygiene — extracting psychological signal from news flows using LLMs.

Deploy it for any news outlet in any country. Point it at your local news source, run it hourly, and watch the patterns emerge.

---

## What it does

The dashboard surfaces **two independent scoring tracks** over the same scraped articles
(scrape once, score twice), shown as two tabs. Both run higher = worse.

| Track | Question | Direction |
|---|---|---|
| **Ragebait Index** | Is this emotion manufactured or authentic? | Higher = more manufactured (worse) |
| **Irreführungs-Index** *(optional)* | Do the article's checkable claims hold up? | Higher = more misleading (worse) |

#### Ragebait Index — four sub-scores (closed-book, Mistral)

| Sub-score | Research basis | What it detects |
|---|---|---|
| `curiosity_gap` | Blom & Hansen (2015) | Headline withholds information to force a click |
| `conflict_staging` | Rony et al. (2017) | Groups artificially pitted against each other |
| `emotional_inflation` | Potthast et al. (2016) | Emotional adjectives without factual backing |
| `narrative_exploitation` | Brady et al. (2017) | Moral outrage farming — villain/victim framing |

#### Irreführungs-Index — three sub-scores (open-book: retrieves external evidence)

The name is the standard German fact-checking verdict term ("irreführend"); the mean of three
sub-scores is the index. **Factual Accuracy abstains to NEI** (FEVER's *NotEnoughInfo*) when the
evidence is thin and is then excluded from the mean — the tool never asserts a named outlet
"lies" without proof.

| Sub-score | Research basis | What it detects |
|---|---|---|
| `factual_accuracy` | FEVER, Thorne et al. (2018) | Do retrieved sources support / refute the claims? *(open-book)* |
| `misleading_framing` | Entman (1993) | Framing pushes a reading beyond what the facts support |
| `missing_context` | Rogers et al. (2017) | Paltering — true statements omit context to mislead |

### Scoring pipeline

```
Tier 1 — Mistral Small    all new articles → pre_score (ragebait) [+ fc pre-flag, optional]
Tier 2 — Mistral Large    top candidates  → 4 parallel sub-scores → composite (ragebait)
Judge  — Mistral Large    compare top results → pick dashboard highlight
Reader Service            factual extract for the judge-selected article

Fact-Check track (optional, FACTCHECK_ENABLED):  winner-only, throttled
  pre-flag (Small) → judge picks 1 of top-5 → claim extraction (Small)
  → evidence: Google Fact Check Tools (free) then Tavily (web) → 3 Large sub-scores → mean
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
| [blick.ch](https://www.blick.ch) | `blick_scraper_connector.py` | Playwright (bot-protected) — **disabled in prod**, see below |
| [nau.ch](https://www.nau.ch) | `nau_scraper_connector.py` | HTTP + JSON-LD |

All scrapers parse JSON-LD `NewsArticle` blocks with trafilatura as fallback.

> **Blick is disabled by default in production.** Its Akamai bot protection returns
> `403 Access Denied` to datacenter IP ranges (Infomaniak/Jelastic) across the whole
> `blick.ch` domain — pages, sitemaps and RSS alike — so it cannot be scraped from the
> server. It still works from a residential IP, so it remains in the connector registry
> and can be run explicitly (`run_pipeline.py --sources blick`) from a local machine.
> A default run uses `DEFAULT_SOURCES` (all sources minus `config.DISABLED_SOURCES`).
> Because Blick is prod-disabled, the Docker image ships **without** Playwright/Chromium;
> to scrape Blick locally first run `pip install playwright && playwright install chromium`.
> To collect Blick legitimately at scale, use a licensed source (e.g. Swissdox@LiRI, the
> Swiss media archive) or request IP whitelisting from Ringier.

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

# Optional — Fact-Check track (Irreführungs-Index). The ragebait track runs
# without these; each retrieval backend self-skips if its key is blank.
GOOGLE_FACTCHECK_API_KEY=your_google_factcheck_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

#### Enabling the Fact-Check track (optional)

The second track is **off by default** (`FACTCHECK_ENABLED = False` in `src/config.py`). To turn
it on:

1. **Get the keys** (both have free tiers):
   - **Google Fact Check Tools** — in [Google Cloud Console](https://console.cloud.google.com),
     enable the *Fact Check Tools API*, then create an **API key** (Credentials → Create
     Credentials → API key). Reads only public data, so no OAuth/billing flow is needed.
   - **Tavily** — sign up at [app.tavily.com](https://app.tavily.com) and copy your `tvly-…` key
     (~1000 free credits/month).
2. Put both keys in `.env` (above).
3. Set `FACTCHECK_ENABLED = True` in `src/config.py`.

It is **winner-only and throttled** (`FACTCHECK_EVERY_N_RUNS`, default every ~6h) so Tavily stays
inside the free tier: only the single judge-picked article per run hits the paid web search
(budget ≈ articles × claims × runs/day; keep it under ~33/day for Tavily's free 1000/month).

### 3. Start everything

```bash
docker compose up -d
```

Starts three containers: `db` (PostgreSQL 16), `frontend` (Streamlit, served on container
port 8080 and mapped to host 8501), `scheduler` (hourly pipeline).

Open [http://localhost:8501](http://localhost:8501).

### Run the pipeline manually

```bash
# One-shot via Docker:
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

# Optional — only if the Fact-Check track is enabled (FACTCHECK_ENABLED).
# Leave unset to run the ragebait track only; retrieval self-skips on a blank key.
GOOGLE_FACTCHECK_API_KEY=your_google_factcheck_api_key
TAVILY_API_KEY=your_tavily_api_key
```

The PostgreSQL hostname, user, and password are shown in the Jelastic DB node details panel.
The two fact-check keys are also declared in `jelastic.jps.example`, so a fresh install/recreate
from the manifest prompts for them.

**4. Web port**

Streamlit serves on port `8080`, which Jelastic's load balancer routes the environment
URL to automatically (`JELASTIC_PRIORITY_PORTS=8080`) — no manual endpoint mapping needed.
The dashboard is reachable at the environment's `https://<env>.jcloud.ik-server.com` URL
(bind a custom domain + SSL under Settings if desired).

**5. Add the webhook secret to GitHub**

The deploy workflow triggers the redeploy by calling the Jelastic REST API. Generate a
personal **access token** in the Jelastic console (account menu → Settings → Access
Tokens, environment scope, short expiry), then assemble the redeploy URL:

```
https://app.<your-jelastic-host>/1.0/environment/control/rest/redeploycontainersbygroup?envName=<env-name>&nodeGroup=cp&tag=latest&token=<access-token>
```

For Infomaniak the host is `app.jpc.infomaniak.com`, and `nodeGroup=cp` is the Docker
app-server node defined in `jelastic.jps`. Add the assembled URL as a repository secret
(Settings → Secrets and variables → Actions → New secret):

| Secret | Value |
|---|---|
| `JELASTIC_WEBHOOK_PROD` | The full `redeploycontainersbygroup` REST URL above (it embeds the access token) |

The token is sensitive — it lives only in the GitHub secret, never in the repo. Rotate
it from the Jelastic console if it ever leaks.

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

Create a file in `src/connectors/specific_scraper/` extending `BaseScraperConnector`
(or `BasePlaywrightScraperConnector` for bot-protected sites that need a real browser).
Declare the crawl targets as class attributes and implement three methods — the shared
crawl loop, JSON-LD parsing, rate limiting and dedup are all inherited:

```python
from typing import Optional
from src.connectors.abstract.scraper_connector import BaseScraperConnector
from src.connectors.abstract.models import Article

class MyNewsConnector(BaseScraperConnector):
    SOURCE = "mynews.com"
    LANGUAGE = "en"
    BASE_URL = "https://mynews.com"
    DEFAULT_SECTIONS = ["/", "/politics", "/world"]   # each joined onto BASE_URL
    CRAWL_DELAY = 1.0                                  # seconds between article fetches

    def extract_article_links(self, html: str, index_url: str) -> list[str]:
        # Return absolute article URLs found on an index/section page
        ...

    def parse_article(self, html: str, url: str) -> Article:
        # Parse a single article page into an Article
        ...

    @staticmethod
    def _extract_article_id(url: str) -> Optional[str]:
        # Return a stable unique ID from the URL (for dedup)
        ...
```

Then register it in the `CONNECTORS` dict in `src/pipeline.py`:

```python
CONNECTORS = {
    # ...existing sources...
    "mynews": MyNewsConnector,
}
```

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
├── scheduler.py                 # hourly loop — runs run_pipeline.py as a one-shot subprocess
├── start.sh                     # container entrypoint: scheduler + frontend
├── pytest.ini                   # test configuration
├── pyproject.toml               # packaging — `pip install -e .` makes src importable
├── src/
│   ├── pipeline.py              # core pipeline logic (importable)
│   ├── config.py                # cross-cutting tunables (thresholds, windows)
│   ├── strings.py               # ALL prompts + UI text (German active; English mirror commented)
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
│   │   ├── scorer.py            # Tier-2 + judge: Mistral Large
│   │   ├── schemas.py           # Pydantic schemas
│   │   └── throttle.py          # rate limiter singletons
│   ├── factcheck/               # Fact-Check track (Irreführungs-Index, optional)
│   │   ├── pre_flag.py          # Tier-1 check-worthiness pre-flag (Mistral Small)
│   │   ├── claims.py            # claim extraction (SAFE/Claimify style)
│   │   ├── retrieval.py         # Google Fact Check Tools + Tavily (key-guarded)
│   │   ├── scorer.py            # judge + 3 Large sub-scores → Irreführungs-Index
│   │   └── schemas.py           # Pydantic schemas (evidence, verdict)
│   └── frontend/
│       ├── app.py               # Streamlit dashboard — st.tabs(Ragebait, Faktencheck)
│       ├── data.py              # DB queries + highlight selection (both tracks)
│       ├── components.py        # HTML builders for the dashboard cards
│       └── styles.py            # CSS + theming
├── tests/
│   ├── conftest.py              # shared fixtures + skip conditions
│   ├── test_connectors.py       # unit tests — all 4 scrapers (no network/DB)
│   ├── test_factcheck.py        # unit tests — retrieval, scorer (NEI mean), cadence
│   ├── test_pipeline.py         # unit tests — source enablement + scrape watchdog
│   ├── test_integration_scraper.py   # integration — scrape + DB upsert
│   └── test_integration_scoring.py  # integration — pre-score + full score
├── migrations/
│   ├── migrate_v3_to_v4.py
│   └── migrate_v4_to_v5.py
├── Dockerfile
├── docker-compose.yml           # local dev: db + frontend + scheduler + worker
├── docker-compose.prod.yml      # production overrides
├── jelastic.jps.example         # Jelastic IaC — recreates the full prod environment
├── .github/workflows/
│   └── deploy-prod.yml          # CI/CD: build image → ghcr.io → Jelastic redeploy
├── .env.example                 # environment-variable template
└── requirements.txt
```

---

## Localisation (running in another language)

All human- and model-facing text — every Mistral prompt template **and** every dashboard
string — lives in a single file, [`src/strings.py`](src/strings.py). The live product runs in
German (de-CH); a complete **English mirror** sits fully commented out at the bottom of the same
file, defining the same names. To run the whole stack in English (or to fork into another
language), comment out the German block and uncomment the English one — most editors block-toggle
a selection in one shortcut. No logic changes: the modules import names from `src.strings` and only
fill in `{placeholders}`. Prompt text is byte-sensitive (Tier-2 runs at temperature 0.0 + seed 42),
so keep both language copies in sync when you edit a prompt.

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

### Fact-Check track (Irreführungs-Index)

| Paper | DOI / link |
|---|---|
| Thorne et al. (2018) — FEVER: Fact Extraction and VERification | [aclanthology.org/N18-1074](https://aclanthology.org/N18-1074/) |
| Entman (1993) — Framing: Toward Clarification of a Fractured Paradigm | [10.1111/j.1460-2466.1993.tb01304.x](https://doi.org/10.1111/j.1460-2466.1993.tb01304.x) |
| Rogers et al. (2017) — Artful Paltering | [10.1037/pspi0000081](https://doi.org/10.1037/pspi0000081) |
| Hassan et al. (2017) — ClaimBuster (check-worthiness) | [10.1145/3097983.3098131](https://doi.org/10.1145/3097983.3098131) |
| Wardle & Derakhshan (2017) — Information Disorder (Council of Europe) | [coe.int report](https://rm.coe.int/information-disorder-toward-an-interdisciplinary-framework-for-researc/168076277c) |
| Vosoughi, Roy & Aral (2018) — The spread of true and false news online | [10.1126/science.aap9559](https://doi.org/10.1126/science.aap9559) |
| Lewandowsky et al. (2012) — Misinformation and Its Correction | [10.1177/1529100612451018](https://doi.org/10.1177/1529100612451018) |
| Roozenbeek & van der Linden et al. (2022) — Psychological inoculation | [10.1126/sciadv.abo6254](https://doi.org/10.1126/sciadv.abo6254) |
