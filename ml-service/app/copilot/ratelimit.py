"""Per-user request limits, so one user can't exhaust the shared LLM quota (Groq's free tier
has per-minute and per-day caps) or the small server. In memory: right for one instance; several
instances would share a Redis counter instead."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int = 20, per_day: int = 300):
        self.limits = ((60.0, per_minute), (86_400.0, per_day))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> float | None:
        """Record a request; returns None if allowed, else the seconds to wait."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.limits[-1][0]:
                hits.popleft()
            for window, limit in self.limits:
                recent = [t for t in hits if now - t < window]
                if len(recent) >= limit:
                    return round(window - (now - recent[0]), 1)
            hits.append(now)
            return None
