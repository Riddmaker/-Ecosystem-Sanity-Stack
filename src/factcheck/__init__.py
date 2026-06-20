"""
Fact-Check scoring track (Irreführungs-Index).

Second scoring track alongside the Ragebait Index, reusing the same scraped
articles. Open-book: it retrieves external evidence and may abstain (NEI).

Tier-1 here is a cheap *pre-flag* (check-worthiness / suspicion of unverified
claims) with Mistral Small; the most-suspicious articles then get the
grounded Tier-2 verdict. The whole track is gated behind
config.FACTCHECK_ENABLED, so while it is off the ragebait pipeline and local
dev behave exactly as before.
"""
