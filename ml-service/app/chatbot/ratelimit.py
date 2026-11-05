"""Per-user message limits, so one user can't use up the shared free Groq quota. Kept in memory:
right for one server; several would share a counter in Redis."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int):
        self.limits = ((60.0, per_minute), (86_400.0, per_day))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> float | None:
        """Record a request. Returns None if it's allowed, else the seconds to wait."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.limits[-1][0]:
                hits.popleft()
            for window, limit in self.limits:
                recent = [hit for hit in hits if now - hit < window]
                if len(recent) >= limit:
                    return round(window - (now - recent[0]), 1)
            hits.append(now)
            return None
