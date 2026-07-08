"""
Central tunables for the pipeline, scheduler, and frontend.

Model IDs, prompt versions, and rate limits live next to the code that
owns them (src/scoring/*); this module holds the cross-cutting policy
values that were previously scattered as magic numbers.
"""

# ── Tier-2 gate ──────────────────────────────────────────────────────
# Pre-score threshold a candidate must reach to enter the qualitative gate
GATE_MIN_PRE_SCORE = 3.0
# Max candidates sent through the gate per run
GATE_CANDIDATE_LIMIT = 12

# ── Paywall / teaser detection ───────────────────────────────────────
# Blick marks paid content with "(B+)" in the title (matched lowercased)
PAYWALL_TITLE_MARKER = "(b+)"
# Below this word count an article is treated as teaser-only and skipped
MIN_ARTICLE_WORDS = 100
# Below this word count the reader service is skipped (hallucination risk)
MIN_READER_SERVICE_WORDS = 80

# ── Sources ──────────────────────────────────────────────────────────
# Sources excluded from a default pipeline run. Blick sits behind Akamai
# bot protection that returns 403 to datacenter IP ranges (Infomaniak/
# Jelastic), so the whole domain — pages, sitemaps and RSS — is blocked in
# production. It still works from a residential IP, so it stays in the
# CONNECTORS registry and can be run explicitly (e.g. `--sources blick`)
# from a local machine; it is just skipped by default.
DISABLED_SOURCES = ["blick"]

# Hard wall-clock cap per source in _scrape(). A misbehaving connector
# (e.g. a Playwright navigation that ignores its own timeout against a bot
# wall) is abandoned after this many seconds so it can never freeze the
# whole run. HTTP connectors finish well within this via their 15s request
# timeouts; this only ever bites a stuck browser source.
SCRAPE_SOURCE_TIMEOUT = 240

# ── Scheduler ────────────────────────────────────────────────────────
# Lookback window per hourly run; overlap guards against articles that
# publish slightly before the previous run window
SCHEDULE_LOOKBACK_HOURS = 1.5

# ── Fact-Check track (Irreführungs-Index) ────────────────────────────
# Second scoring track, reusing the same scraped articles as the ragebait
# track (scrape once, two tracks). It is open-book — it retrieves external
# evidence — so it carries extra cost and is gated behind this master
# switch. While False the pipeline skips every fact-check stage, so the
# ragebait track and local dev behave exactly as before.
FACTCHECK_ENABLED = True

# Suspicion pre-flag threshold (Tier-1, Mistral Small, 0–10). An article
# must reach this to enter fact-checking — mirrors GATE_MIN_PRE_SCORE.
FACTCHECK_SUSPICION_THRESHOLD = 3.0

# Max articles fact-checked per run — the N most-suspicious above the
# threshold. Only these get claim extraction + evidence retrieval.
FACTCHECK_CANDIDATE_LIMIT = 5

# Max checkable claims extracted per article; caps evidence-retrieval cost
# (and the Tavily free-tier budget) on long articles.
FACTCHECK_MAX_CLAIMS = 3

# Cadence throttle: run the fact-check track only every Nth pipeline run.
# 1 = every run (hourly, same as ragebait); a larger value slows it down to
# protect the retrieval free-tier budget. Winner-only Tavily means the budget
# is articles(1) x claims x runs/day; keep it under ~33/day for the Tavily
# free tier (1000 credits/mo). E.g. 6 ≈ every 6h.
FACTCHECK_EVERY_N_RUNS = 6

# ── Fact-Check retrieval (Google Fact Check Tools + Tavily) ──────────
# Google Fact Check Tools — first pass: has this claim already been debunked?
GOOGLE_FC_LANGUAGE  = "de"     # BCP-47 language code for the claims:search filter
GOOGLE_FC_PAGE_SIZE = 5        # ClaimReview verdicts to pull per claim lookup
# Tavily — novel-claim web evidence (winner only). search_depth is pinned to
# "basic" (1 credit) in retrieval.py; these shape WHAT comes back.
TAVILY_TOPIC       = "news"    # bias toward news sources over the general web
TAVILY_TIME_RANGE  = "month"   # recency window ("day"/"week"/"month"/"year" or "")
TAVILY_MAX_RESULTS = 5         # ranked results per claim
# Minimum Tavily relevance (0–1) for a web result to count as evidence. Tavily
# always returns its best-effort top-N, even for a hyperlocal claim its index
# can't match — a Swiss-German hedgehog claim once drew IPL cricket highlights at
# ~0.02. That junk then reached both the scorer prompt and the "Belege" UI. Drop
# anything below this floor; if it empties a claim's evidence, the scorer honestly
# abstains to NEI. Genuine on-topic hits score well above this. Tunable.
TAVILY_MIN_RELEVANCE = 0.30

# ── Frontend ─────────────────────────────────────────────────────────
# Window for "articles screened in the latest batch" stats; slightly
# larger than the hourly pipeline cadence so one full run always fits
BATCH_WINDOW_MINUTES = 75
