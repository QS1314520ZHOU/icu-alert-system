"""Generic in-memory TTL cache for API endpoint responses.

Usage::

    from app.utils.cache import TTLCache

    _cache = TTLCache(ttl_seconds=30)

    @router.get("/api/some-endpoint")
    async def handler(params: str):
        cache_key = f"some-endpoint:{params}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        result = await expensive_query()
        _cache.set(cache_key, result)
        return result
"""

from __future__ import annotations

import hashlib
import json
from threading import Lock
from time import monotonic
from typing import Any


class TTLCache:
    """Thread-safe in-memory cache with per-entry TTL expiration.

    Parameters
    ----------
    ttl_seconds : int
        Default time-to-live in seconds for each cache entry.
    max_entries : int
        Maximum number of entries to keep. When exceeded, the oldest
        entries are evicted.  0 means unlimited.
    """

    def __init__(self, ttl_seconds: int = 30, max_entries: int = 256):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    # ── public API ──────────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        """Return cached value if present and not expired, else ``None``."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if (monotonic() - ts) < self._ttl:
                return value
            # expired – remove lazily
            del self._store[key]
            return None

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key*, evicting oldest if over capacity."""
        with self._lock:
            self._store[key] = (monotonic(), value)
            if 0 < self._max < len(self._store):
                self._evict_oldest()

    def invalidate(self, key: str | None = None) -> None:
        """Remove a specific key, or clear all entries if *key* is ``None``."""
        with self._lock:
            if key is not None:
                self._store.pop(key, None)
            else:
                self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    # ── helpers ─────────────────────────────────────────────────

    def _evict_oldest(self) -> None:
        """Remove the oldest entry (must be called with lock held)."""
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k][0])
        del self._store[oldest_key]


def make_cache_key(*parts: Any) -> str:
    """Build a deterministic cache key from arbitrary parts.

    Large values (lists, dicts) are hashed to keep keys short.
    """
    segments: list[str] = []
    for p in parts:
        if isinstance(p, (list, dict)):
            segments.append(hashlib.md5(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:12])
        else:
            segments.append(str(p))
    return ":".join(segments)
