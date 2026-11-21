from __future__ import annotations


class NullCacheBackend:
    """No-op cache backend for --no-cache and none:// URIs."""

    async def get(self, key: str) -> bytes | None:
        return None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def close(self) -> None:
        return None
