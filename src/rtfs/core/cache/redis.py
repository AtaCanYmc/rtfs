from __future__ import annotations

from typing import Any

from rtfs.core.cache.base import CacheInfo

DEFAULT_TTL = 86400 * 7


def _sanitize_redis_url(url: str) -> str:
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    auth_end = len(rest)
    for delim in ("/", "?", "#"):
        idx = rest.find(delim)
        if idx != -1 and idx < auth_end:
            auth_end = idx
    authority = rest[:auth_end]
    if "@" not in authority:
        return url
    _, _, host_part = authority.rpartition("@")
    return f"{scheme}://{host_part}{rest[auth_end:]}"


def _escape_redis_glob(prefix: str) -> str:
    return "".join(f"\\{ch}" if ch in r"\*?[]" else ch for ch in prefix)


class RedisCacheBackend:
    """Async Redis cache backend using redis.asyncio."""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "rtfs:",
        default_ttl: int | None = DEFAULT_TTL,
        client: Any | None = None,
    ) -> None:
        self.url = url
        self.prefix = prefix
        self.default_ttl = default_ttl
        if client is not None:
            self._client = client
        else:
            try:
                import redis.asyncio as redis_async  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ImportError(
                    "Redis backend requires the redis extra: pip install pyrtfs[redis]"
                ) from exc
            self._client = redis_async.from_url(url, decode_responses=False)

    def _prefixed(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _matches_prefix(self, key: Any) -> bool:
        if isinstance(key, bytes):
            return key.startswith(self.prefix.encode("utf-8"))
        if isinstance(key, str):
            return key.startswith(self.prefix)
        return False

    @staticmethod
    def _normalize_key(key: bytes | str) -> bytes:
        return key if isinstance(key, bytes) else key.encode("utf-8", "surrogateescape")

    async def get(self, key: str) -> bytes | None:
        val = await self._client.get(self._prefixed(key))
        if isinstance(val, bytes):
            return val
        if isinstance(val, str):
            return val.encode("utf-8")
        return None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        expire = self.default_ttl if ttl is None else ttl
        await self._client.set(self._prefixed(key), value, ex=expire)

    async def delete(self, key: str) -> None:
        await self._client.delete(self._prefixed(key))

    async def clear(self) -> None:
        if not hasattr(self._client, "scan"):
            return
        pattern = f"{_escape_redis_glob(self.prefix)}*"
        cursor: int | bytes | str = 0
        seen_keys: set[bytes] = set()
        keys_to_delete: list[bytes | str] = []
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor,
                match=pattern,
                count=500,
            )
            for key in keys:
                if not self._matches_prefix(key):
                    continue
                norm = self._normalize_key(key)
                if norm not in seen_keys:
                    seen_keys.add(norm)
                    keys_to_delete.append(key)
            if cursor in (0, b"0", "0"):
                break
        for idx in range(0, len(keys_to_delete), 500):
            batch = keys_to_delete[idx : idx + 500]
            await self._client.delete(*batch)

    async def info(self) -> CacheInfo:
        entries: int | None = None
        if hasattr(self._client, "scan"):
            pattern = f"{_escape_redis_glob(self.prefix)}*"
            cursor: int | bytes | str = 0
            seen_keys: set[bytes] = set()
            while True:
                cursor, keys = await self._client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=500,
                )
                for key in keys:
                    if self._matches_prefix(key):
                        seen_keys.add(self._normalize_key(key))
                if cursor in (0, b"0", "0"):
                    break
            entries = len(seen_keys)

        size_bytes: int | None = None
        if hasattr(self._client, "info"):
            try:
                mem_info = await self._client.info("memory")
                if isinstance(mem_info, dict):
                    used = mem_info.get("used_memory")
                    if isinstance(used, (int, float)) and not isinstance(used, bool):
                        size_bytes = int(used)
            except Exception:
                size_bytes = None

        return CacheInfo(
            backend="redis",
            location=_sanitize_redis_url(self.url),
            entries=entries,
            size_bytes=size_bytes,
        )

    async def close(self) -> None:
        if hasattr(self._client, "aclose"):
            await self._client.aclose()
        elif hasattr(self._client, "close"):
            res = self._client.close()
            if hasattr(res, "__await__"):
                await res
