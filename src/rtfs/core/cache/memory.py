from __future__ import annotations

import time

from rtfs.core.cache.base import CacheInfo


class MemoryCacheBackend:
    """In-memory bytes cache with monotonic TTL expiration."""

    def __init__(self, default_ttl: int | None = None) -> None:
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[bytes, float | None]] = {}

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, (_, expires_at) in self._store.items()
            if expires_at is not None and now >= expires_at
        ]
        for key in expired:
            del self._store[key]

    async def get(self, key: str) -> bytes | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        effective_ttl = self.default_ttl if ttl is None else ttl
        expires_at = (
            time.monotonic() + effective_ttl
            if effective_ttl is not None
            else None
        )
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    async def info(self) -> CacheInfo:
        self._prune_expired()
        size_bytes = sum(len(value) for value, _ in self._store.values())
        return CacheInfo(
            backend="memory",
            location=None,
            entries=len(self._store),
            size_bytes=size_bytes,
        )

    async def close(self) -> None:
        self._store.clear()
