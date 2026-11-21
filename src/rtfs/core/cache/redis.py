from __future__ import annotations

from typing import Any

DEFAULT_TTL = 86400 * 7


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

    async def close(self) -> None:
        if hasattr(self._client, "aclose"):
            await self._client.aclose()
        elif hasattr(self._client, "close"):
            res = self._client.close()
            if hasattr(res, "__await__"):
                await res
