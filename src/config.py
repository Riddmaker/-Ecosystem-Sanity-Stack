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
FACTCHECK_ENABLED = False

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
# protect the retrieval free-tier budget. The cadence decision sets this.
FACTCHECK_EVERY_N_RUNS = 1

# ── Frontend ─────────────────────────────────────────────────────────
# Window for "articles screened in the latest batch" stats; slightly
# larger than the hourly pipeline cadence so one full run always fits
BATCH_WINDOW_MINUTES = 75
