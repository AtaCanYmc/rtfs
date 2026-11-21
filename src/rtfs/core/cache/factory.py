from __future__ import annotations

import os

from rtfs.core.cache.base import CacheBackend
from rtfs.core.cache.disk import DiskCacheBackend
from rtfs.core.cache.memory import MemoryCacheBackend
from rtfs.core.cache.null import NullCacheBackend
from rtfs.core.cache.redis import RedisCacheBackend

DEFAULT_CACHE_URL = "disk://~/.cache/rtfs"


def _extract_redis_host(url: str) -> str:
    _, _, rest = url.partition("://")
    auth_end = len(rest)
    for delim in ("/", "?", "#"):
        idx = rest.find(delim)
        if idx != -1 and idx < auth_end:
            auth_end = idx
    authority = rest[:auth_end]
    host_port = authority.rpartition("@")[2]
    if host_port.startswith("["):
        end_bracket = host_port.find("]")
        if end_bracket == -1:
            return ""
        trailing = host_port[end_bracket + 1 :]
        if trailing and not trailing.startswith(":"):
            return ""
        return host_port[1:end_bracket].strip()
    host, _, _ = host_port.partition(":")
    return host.strip()


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
        if not _extract_redis_host(resolved):
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
