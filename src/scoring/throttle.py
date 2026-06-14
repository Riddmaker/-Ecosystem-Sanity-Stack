"""
Global, thread-safe API rate limiters.

One limiter per Mistral tier so that all callers within a process
share the same token bucket — avoiding bursts when multiple scorer
instances or parallel threads fire simultaneously.
"""

import threading
import time

# Per-workspace Mistral limits — see admin.mistral.ai/plateforme/limits.
# The Large tier is the binding constraint at 0.25 RPS (1 request / 4s); pace
# just under it so bursts don't 429. Setting this to 1/s (the old value) let
# requests through 4x too fast and caused a storm of 429 backoffs. The Small
# (pre-score) tier RPS is far higher, so 5/s stays comfortably under it.
_MAX_LARGE = 0.24   # req/sec for mistral-large-* — workspace limit is 0.25 RPS
_MAX_SMALL = 5      # req/sec for mistral-small-* (separate pool, higher RPS limit)


class _RateLimiter:
    def __init__(self, max_per_second: float) -> None:
        self._interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last: float = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            gap = self._interval - elapsed
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()


# Module-level singletons — import and call .wait() directly
large_limiter = _RateLimiter(_MAX_LARGE)
small_limiter = _RateLimiter(_MAX_SMALL)
