from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from rtfs.core.cache import (
    CacheBackend,
    DiskCacheBackend,
    MemoryCacheBackend,
    NullCacheBackend,
    RedisCacheBackend,
    create_cache,
)


async def test_memory_cache_backend() -> None:
    cache = MemoryCacheBackend()
    assert isinstance(cache, CacheBackend)

    assert await cache.get("k1") is None
    await cache.set("k1", b"payload-1")
    assert await cache.get("k1") == b"payload-1"

    await cache.delete("k1")
    assert await cache.get("k1") is None

    # TTL expiration
    await cache.set("expiring", b"short-lived", ttl=0)
    await asyncio.sleep(0.01)
    assert await cache.get("expiring") is None

    await cache.set("k2", b"payload-2")
    await cache.close()
    assert await cache.get("k2") is None


async def test_disk_cache_backend(tmp_path: Path) -> None:
    cache_dir = tmp_path / "disk_cache"
    cache = DiskCacheBackend(path=cache_dir)
    assert isinstance(cache, CacheBackend)

    assert await cache.get("script:1") is None
    await cache.set("script:1", b"raw-pdf-bytes", ttl=60)
    assert await cache.get("script:1") == b"raw-pdf-bytes"

    await cache.delete("script:1")
    assert await cache.get("script:1") is None
    await cache.close()


async def test_null_cache_backend() -> None:
    cache = NullCacheBackend()
    assert isinstance(cache, CacheBackend)

    await cache.set("any", b"value", ttl=60)
    assert await cache.get("any") is None
    await cache.delete("any")
    await cache.close()


async def test_create_cache_factory_and_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Explicit URIs
    mem = create_cache("memory://")
    assert isinstance(mem, MemoryCacheBackend)
    await mem.close()

    null = create_cache("none://")
    assert isinstance(null, NullCacheBackend)
    await null.close()

    disk_path = tmp_path / "custom_cache"
    disk = create_cache(f"disk://{disk_path}")
    assert isinstance(disk, DiskCacheBackend)
    assert disk.path == disk_path
    await disk.close()

    # RTFS_CACHE_URL fallback when url is None
    monkeypatch.setenv("RTFS_CACHE_URL", "memory://")
    env_cache = create_cache(None)
    assert isinstance(env_cache, MemoryCacheBackend)
    await env_cache.close()

    # Invalid scheme and malformed URI
    with pytest.raises(ValueError, match="Unsupported cache scheme"):
        create_cache("memcached://localhost:11211")

    with pytest.raises(ValueError, match="Unsupported cache URI"):
        create_cache("invalid_uri_without_scheme")


async def test_redis_cache_backend_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.setitem(sys.modules, "redis.asyncio", None)

    with pytest.raises(
        ImportError,
        match=r"Redis backend requires the redis extra: pip install pyrtfs\[redis\]",
    ):
        RedisCacheBackend("redis://localhost:6379/0")


class _FakeRedisClient:
    def __init__(self) -> None:
        self.store: dict[str, tuple[bytes, int | None]] = {}
        self.closed = False

    async def get(self, key: str) -> bytes | None:
        item = self.store.get(key)
        return item[0] if item else None

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.store[key] = (value, ex)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def aclose(self) -> None:
        self.closed = True


async def test_redis_cache_backend_with_mock_client() -> None:
    fake_client: Any = _FakeRedisClient()
    backend = RedisCacheBackend(
        url="redis://localhost:6379/0",
        prefix="rtfs_test:",
        default_ttl=120,
        client=fake_client,
    )
    assert isinstance(backend, CacheBackend)

    assert await backend.get("k1") is None
    await backend.set("k1", b"redis-bytes")
    assert fake_client.store["rtfs_test:k1"] == (b"redis-bytes", 120)
    assert await backend.get("k1") == b"redis-bytes"

    await backend.delete("k1")
    assert await backend.get("k1") is None

    await backend.close()
    assert fake_client.closed is True
