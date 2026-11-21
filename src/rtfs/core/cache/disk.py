from __future__ import annotations

import asyncio
from pathlib import Path

from diskcache import Cache

DEFAULT_CACHE_DIR = Path("~/.cache/rtfs")
DEFAULT_TTL = 86400 * 7


class DiskCacheBackend:
    """Async wrapper over SQLite-backed diskcache storing raw bytes."""

    def __init__(
        self,
        path: str | Path = DEFAULT_CACHE_DIR,
        default_ttl: int | None = DEFAULT_TTL,
    ) -> None:
        self.path = Path(path).expanduser()
        self.default_ttl = default_ttl
        self._cache = Cache(str(self.path))

    async def get(self, key: str) -> bytes | None:
        val = await asyncio.to_thread(self._cache.get, key, default=None)
        if isinstance(val, bytes):
            return val
        return None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        expire = self.default_ttl if ttl is None else ttl
        await asyncio.to_thread(self._cache.set, key, value, expire=expire)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._cache.delete, key)

    async def clear(self) -> None:
        await asyncio.to_thread(self._cache.clear)

    async def close(self) -> None:
        await asyncio.to_thread(self._cache.close)
