from __future__ import annotations

import os
from urllib.parse import urlparse

from rtfs.core.cache.base import CacheBackend
from rtfs.core.cache.disk import DiskCacheBackend
from rtfs.core.cache.memory import MemoryCacheBackend
from rtfs.core.cache.null import NullCacheBackend
from rtfs.core.cache.redis import RedisCacheBackend

DEFAULT_CACHE_URL = "disk://~/.cache/rtfs"


def create_cache(url: str | None = None) -> CacheBackend:
    """Instantiate a CacheBackend from a URI string or RTFS_CACHE_URL environment variable."""
    resolved = url if url is not None else os.getenv("RTFS_CACHE_URL", DEFAULT_CACHE_URL)
    resolved = resolved.strip()

    if "://" not in resolved:
        raise ValueError(
            f"Unsupported cache URI '{resolved}'. Expected scheme://... "
            "(supported: disk://, redis://, rediss://, memory://, none://)"
        )

    scheme, remainder = resolved.split("://", 1)
    scheme_lower = scheme.lower()

    if scheme_lower == "disk":
        raw_path = remainder.strip() or "~/.cache/rtfs"
        return DiskCacheBackend(raw_path)

    if scheme_lower in {"redis", "rediss"}:
        parsed = urlparse(resolved)
        if not parsed.netloc:
            raise ValueError(f"Invalid Redis URI '{resolved}': missing host")
        return RedisCacheBackend(resolved)

    if scheme_lower == "memory":
        return MemoryCacheBackend()

    if scheme_lower == "none":
        return NullCacheBackend()

    raise ValueError(
        f"Unsupported cache scheme '{scheme_lower}' in '{resolved}'. "
        "Supported schemes: disk, redis, rediss, memory, none"
    )
