"""
Global, thread-safe API rate limiters.

One limiter per Mistral tier so that all callers within a process
share the same token bucket — avoiding bursts when multiple scorer
instances or parallel threads fire simultaneously.
"""

import threading
import time

_MAX_LARGE = 1   # req/sec for mistral-large-* — 1/s to respect plan burst limits
_MAX_SMALL = 5   # req/sec for mistral-small-* (separate pool)


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
