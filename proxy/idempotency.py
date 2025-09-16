from __future__ import annotations

import asyncio
import time
from typing import Dict, Generic, Optional, TypeVar


T = TypeVar("T")


class IdempotencyCache(Generic[T]):
    """An in-memory cache with TTL semantics used for idempotent responses."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: Dict[str, tuple[float, T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[T]:
        async with self._lock:
            self._prune()
            entry = self._store.get(key)
            if not entry:
                return None
            timestamp, value = entry
            if time.monotonic() - timestamp > self._ttl_seconds:
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            self._prune()
            self._store[key] = (time.monotonic(), value)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def _prune(self) -> None:
        if not self._store:
            return
        cutoff = time.monotonic() - self._ttl_seconds
        expired = [cache_key for cache_key, (ts, _) in self._store.items() if ts < cutoff]
        for cache_key in expired:
            self._store.pop(cache_key, None)
