from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from diskcache import Cache

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "rtfs"


class ScriptCache:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, ttl: int = 86400 * 7) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl
        self._cache = Cache(str(cache_dir))

    @staticmethod
    def _key(prefix: str, identifier: str) -> str:
        digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        return f"{prefix}:{digest}"

    def get(self, prefix: str, identifier: str) -> Any | None:
        return self._cache.get(self._key(prefix, identifier))

    def set(self, prefix: str, identifier: str, value: Any) -> None:
        self._cache.set(self._key(prefix, identifier), value, expire=self.ttl)

    def clear(self) -> None:
        self._cache.clear()

    def close(self) -> None:
        self._cache.close()
