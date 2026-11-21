from __future__ import annotations

import time


class MemoryCacheBackend:
    """In-memory bytes cache with monotonic TTL expiration."""

    def __init__(self, default_ttl: int | None = None) -> None:
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[bytes, float | None]] = {}

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

    async def close(self) -> None:
        self._store.clear()
