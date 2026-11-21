from __future__ import annotations

import asyncio
import re
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from rtfs.core.cache import (
    CacheBackend,
    CacheInfo,
    DiskCacheBackend,
    MemoryCacheBackend,
    NullCacheBackend,
    RedisCacheBackend,
    create_cache,
)
from rtfs.core.cache.redis import _sanitize_redis_url


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


def _redis_glob_match(value: str, pattern: str) -> bool:
    regex_parts = [r"\A"]
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\" and i + 1 < n:
            regex_parts.append(re.escape(pattern[i + 1]))
            i += 2
        elif ch == "*":
            regex_parts.append(".*")
            i += 1
        elif ch == "?":
            regex_parts.append(".")
            i += 1
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                if pattern[j] == "\\" and j + 1 < n:
                    j += 2
                else:
                    j += 1
            if j >= n:
                regex_parts.append(re.escape(ch))
                i += 1
            else:
                regex_parts.append(pattern[i : j + 1])
                i = j + 1
        else:
            regex_parts.append(re.escape(ch))
            i += 1
    regex_parts.append(r"\Z")
    return re.match("".join(regex_parts), value, flags=re.DOTALL) is not None


class _FakeRedisClient:
    def __init__(self, used_memory: int = 4096, page_size: int = 2) -> None:
        self.store: dict[str, tuple[bytes, int | None]] = {}
        self.closed = False
        self.used_memory = used_memory
        self.page_size = page_size
        self.raise_on_info = False
        self._scan_snapshot: list[str] = []

    async def get(self, key: str) -> bytes | None:
        item = self.store.get(key)
        return item[0] if item else None

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self.store[key] = (value, ex)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)

    async def scan(
        self,
        cursor: int | bytes | str = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        idx = int(cursor) if isinstance(cursor, (int, str, bytes)) else 0
        if idx == 0:
            self._scan_snapshot = sorted(
                key
                for key in self.store
                if match is None or _redis_glob_match(key, match)
            )
        step = self.page_size if self.page_size > 0 else len(self._scan_snapshot) or 1
        batch = [k for k in self._scan_snapshot[idx : idx + step] if k in self.store]
        next_cursor = idx + step if idx + step < len(self._scan_snapshot) else 0
        return next_cursor, batch

    async def info(self, section: str | None = None) -> dict[str, Any]:
        if self.raise_on_info:
            raise RuntimeError("NOPERM INFO command disabled")
        return {"used_memory": self.used_memory}

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


async def test_memory_cache_info_and_clear() -> None:
    cache = MemoryCacheBackend()
    assert await cache.info() == CacheInfo(
        backend="memory",
        location=None,
        entries=0,
        size_bytes=0,
    )

    await cache.set("live", b"1234", ttl=60)
    await cache.set("expired", b"56789", ttl=0)
    await asyncio.sleep(0.01)

    info = await cache.info()
    assert info == CacheInfo(
        backend="memory",
        location=None,
        entries=1,
        size_bytes=4,
    )

    await cache.clear()
    assert await cache.get("live") is None
    assert await cache.info() == CacheInfo(
        backend="memory",
        location=None,
        entries=0,
        size_bytes=0,
    )


async def test_disk_cache_info_and_clear(tmp_path: Path) -> None:
    cache_dir = tmp_path / "disk_info_cache"
    cache = DiskCacheBackend(path=cache_dir)

    empty_info = await cache.info()
    assert empty_info.backend == "disk"
    assert empty_info.location == str(cache_dir)
    assert empty_info.entries == 0
    assert empty_info.size_bytes is not None and empty_info.size_bytes >= 0

    await cache.set("live", b"abcdef", ttl=60)
    await cache.set("short", b"xyz", ttl=0.05)
    await asyncio.sleep(0.1)

    populated_info = await cache.info()
    assert populated_info.backend == "disk"
    assert populated_info.location == str(cache_dir)
    assert populated_info.entries == 1
    assert populated_info.size_bytes is not None and populated_info.size_bytes > 0

    await cache.clear()
    assert await cache.get("live") is None
    cleared_info = await cache.info()
    assert cleared_info.entries == 0
    await cache.close()


async def test_null_cache_info_and_clear() -> None:
    cache = NullCacheBackend()
    await cache.set("any", b"value", ttl=60)
    await cache.clear()
    assert await cache.info() == CacheInfo(
        backend="null",
        location=None,
        entries=0,
        size_bytes=0,
    )


async def test_redis_cache_info_clear_prefix_isolation_and_url_sanitization() -> None:
    fake_client = _FakeRedisClient(used_memory=8192, page_size=2)
    fake_client.store["other:keep"] = (b"untouched", None)

    backend = RedisCacheBackend(
        url="redis://admin:supersecret@redis.internal:6379/2",
        prefix="rtfs:",
        client=fake_client,
    )
    await backend.set("a", b"one")
    await backend.set("b", b"two")
    await backend.set("c", b"three")

    info = await backend.info()
    assert info == CacheInfo(
        backend="redis",
        location="redis://redis.internal:6379/2",
        entries=3,
        size_bytes=8192,
    )

    await backend.clear()
    assert await backend.get("a") is None
    assert await backend.get("b") is None
    assert await backend.get("c") is None
    assert fake_client.store["other:keep"] == (b"untouched", None)

    # Info gracefully handles restricted INFO command and sanitizes IPv6 URLs
    fake_client.raise_on_info = True
    ipv6_backend = RedisCacheBackend(
        url="rediss://:pw@[::1]:6380/0",
        prefix="rtfs:",
        client=fake_client,
    )
    ipv6_info = await ipv6_backend.info()
    assert ipv6_info == CacheInfo(
        backend="redis",
        location="rediss://[::1]:6380/0",
        entries=0,
        size_bytes=None,
    )


@pytest.mark.parametrize(
    ("prefix", "victim_key"),
    [
        ("rtfs[1]:", "rtfs1:victim"),
        ("rtfs*:", "rtfs_other:victim"),
        ("rtfs?:", "rtfsX:victim"),
        (r"a\b:", "ab:victim"),
    ],
)
async def test_redis_cache_glob_prefix_isolation(prefix: str, victim_key: str) -> None:
    fake_client = _FakeRedisClient()
    fake_client.store[victim_key] = (b"keep-me", None)

    backend = RedisCacheBackend(prefix=prefix, client=fake_client)
    await backend.set("k1", b"owned")

    info = await backend.info()
    assert info.entries == 1

    await backend.clear()
    assert await backend.get("k1") is None
    assert fake_client.store[victim_key] == (b"keep-me", None)
    assert (await backend.info()).entries == 0


async def test_redis_cache_literal_prefix_defense_in_depth_on_unfiltered_scan() -> None:
    class _LeakyScanClient(_FakeRedisClient):
        async def scan(
            self,
            cursor: int | bytes | str = 0,
            match: str | None = None,
            count: int | None = None,
        ) -> tuple[int, list[Any]]:
            # Intentionally ignore `match` and yield mixed str/bytes keys
            return 0, [b"rtfs[1]:k1", "rtfs1:victim", b"rtfs1:victim_bytes"]

    fake_client = _LeakyScanClient()
    fake_client.store["rtfs[1]:k1"] = (b"owned", None)
    fake_client.store["rtfs1:victim"] = (b"keep", None)
    fake_client.store["rtfs1:victim_bytes"] = (b"keep2", None)

    backend = RedisCacheBackend(prefix="rtfs[1]:", client=fake_client)
    assert (await backend.info()).entries == 1

    deleted: list[Any] = []
    orig_delete = fake_client.delete

    async def _recording_delete(*keys: Any) -> None:
        deleted.extend(keys)
        await orig_delete(*(k.decode("utf-8") if isinstance(k, bytes) else k for k in keys))

    fake_client.delete = _recording_delete  # type: ignore[method-assign]
    await backend.clear()
    assert deleted == [b"rtfs[1]:k1"]
    assert "rtfs[1]:k1" not in fake_client.store
    assert "rtfs1:victim" in fake_client.store
    assert "rtfs1:victim_bytes" in fake_client.store


async def test_redis_cache_info_deduplicates_scan_pages() -> None:
    class _DuplicateScanClient(_FakeRedisClient):
        async def scan(
            self,
            cursor: int | bytes | str = 0,
            match: str | None = None,
            count: int | None = None,
        ) -> tuple[int, list[str]]:
            if cursor == 0:
                return 1, ["rtfs:a", "rtfs:b"]
            # Repeat "rtfs:a" across pages as allowed by Redis SCAN
            return 0, ["rtfs:a", "rtfs:c", "rtfs:d"]

    fake_client = _DuplicateScanClient()
    backend = RedisCacheBackend(prefix="rtfs:", client=fake_client)
    info = await backend.info()
    assert info.entries == 4


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        ("redis://user:p[a]ss@host:6379/0", "redis://host:6379/0"),
        ("redis://user:secret@host:notaport/0", "redis://host:notaport/0"),
        ("redis://user:pass@host:99999/0", "redis://host:99999/0"),
        ("redis://user:pass@host:-1/0", "redis://host:-1/0"),
        ("unix://:secret@/var/run/redis.sock", "unix:///var/run/redis.sock"),
        ("unix://user:secret@/var/run/redis.sock?db=1", "unix:///var/run/redis.sock?db=1"),
        ("redis://:p@ss:word@host:6379/0", "redis://host:6379/0"),
        (
            "rediss://user:secret@[::1]:6380/2?ssl_cert_reqs=required",
            "rediss://[::1]:6380/2?ssl_cert_reqs=required",
        ),
        ("redis:///var/run/redis.sock", "redis:///var/run/redis.sock"),
        ("redis://localhost:6379/0", "redis://localhost:6379/0"),
    ],
)
async def test_sanitize_redis_url_edge_cases(raw_url: str, expected: str) -> None:
    assert _sanitize_redis_url(raw_url) == expected
    backend = RedisCacheBackend(url=raw_url, client=_FakeRedisClient())
    assert (await backend.info()).location == expected


@pytest.mark.parametrize(
    "invalid_url",
    [
        "redis://user:pass@",
        "rediss://user:pass@",
        "redis://user:pass@/0",
        "redis://user:pass@:6379/0",
        "redis:///0",
        "redis://",
        "redis://[]/0",
    ],
)
def test_create_cache_rejects_missing_redis_host(invalid_url: str) -> None:
    with pytest.raises(ValueError, match="missing host"):
        create_cache(invalid_url)


def test_create_cache_accepts_valid_redis_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    created_urls: list[str] = []
    fake_redis_async = types.ModuleType("redis.asyncio")

    def _from_url(url: str, decode_responses: bool = False) -> _FakeRedisClient:
        created_urls.append(url)
        return _FakeRedisClient()

    fake_redis_async.from_url = _from_url  # type: ignore[attr-defined]
    fake_redis = types.ModuleType("redis")
    fake_redis.asyncio = fake_redis_async  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_redis_async)

    valid_urls = [
        "redis://localhost:6379/0",
        "rediss://user:pass@localhost:6380/1",
        "redis://[::1]:6379/0",
        "redis://user:p[a]ss@host:6379/0",
    ]
    for url in valid_urls:
        cache = create_cache(url)
        assert isinstance(cache, RedisCacheBackend)
        assert cache.url == url
    assert created_urls == valid_urls
