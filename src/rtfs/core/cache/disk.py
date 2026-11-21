from __future__ import annotations

import asyncio
from pathlib import Path

from diskcache import Cache

from rtfs.core.cache.base import CacheInfo

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
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.path.chmod(0o700)
        except OSError:
            pass
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

    async def info(self) -> CacheInfo:
        def _read_info() -> CacheInfo:
            self._cache.expire()
            return CacheInfo(
                backend="disk",
                location=str(self.path),
                entries=len(self._cache),
                size_bytes=int(self._cache.volume()),
            )

        return await asyncio.to_thread(_read_info)

    async def close(self) -> None:
        await asyncio.to_thread(self._cache.close)
