"""A small in-memory cache with per-entry expiry."""

from __future__ import annotations

import time


class TTLCache[T]:
    """Keeps up to `max_entries` values for `ttl_seconds` each, dropping the oldest when full.

    Per process: with several workers each keeps its own copy, which is fine for data that
    is cheap to reload.
    """

    def __init__(self, ttl_seconds: float, max_entries: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None or entry[0] < time.monotonic():
            return None
        return entry[1]

    def put(self, key: str, value: T) -> None:
        self._entries.pop(key, None)
        if len(self._entries) >= self.max_entries:
            # Dicts keep insertion order, so the first key is the oldest entry
            del self._entries[next(iter(self._entries))]
        self._entries[key] = (time.monotonic() + self.ttl_seconds, value)

    def clear(self) -> None:
        self._entries.clear()
