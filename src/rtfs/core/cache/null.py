from __future__ import annotations

from rtfs.core.cache.base import CacheInfo


class NullCacheBackend:
    """No-op cache backend for --no-cache and none:// URIs."""

    async def get(self, key: str) -> bytes | None:
        return None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def clear(self) -> None:
        return None

    async def info(self) -> CacheInfo:
        return CacheInfo(
            backend="null",
            location=None,
            entries=0,
            size_bytes=0,
        )

    async def close(self) -> None:
        return None
