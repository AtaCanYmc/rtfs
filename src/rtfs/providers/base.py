from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from rtfs.core.cache import (
    CacheBackend,
    create_cache,
    decode_raw_script,
    decode_search_results,
    encode_raw_script,
    encode_search_results,
    make_cache_key,
)
from rtfs.core.http import HttpClient
from rtfs.core.models import RawScript, SearchResult


class BaseProvider(ABC):
    name: str = "base"
    format: Literal["screenplay", "transcript"] = "screenplay"

    def __init__(
        self,
        http: HttpClient,
        cache: CacheBackend | str | None = None,
    ) -> None:
        self.http = http
        if isinstance(cache, str):
            self.cache: CacheBackend | None = create_cache(cache)
        else:
            self.cache = cache

    async def _get_cached_search(self, query: str) -> list[SearchResult] | None:
        if self.cache is None:
            return None
        key = make_cache_key(f"search:{self.name}", query.lower())
        raw = await self.cache.get(key)
        return decode_search_results(raw) if raw is not None else None

    async def _set_cached_search(self, query: str, results: list[SearchResult]) -> None:
        if self.cache is None or not results:
            return
        key = make_cache_key(f"search:{self.name}", query.lower())
        await self.cache.set(key, encode_search_results(results))

    async def _get_cached_raw(self, url: str) -> RawScript | None:
        if self.cache is None:
            return None
        key = make_cache_key(f"raw:{self.name}", url)
        raw = await self.cache.get(key)
        return decode_raw_script(raw) if raw is not None else None

    async def _set_cached_raw(self, url: str, script: RawScript) -> None:
        if self.cache is None:
            return
        key = make_cache_key(f"raw:{self.name}", url)
        await self.cache.set(key, encode_raw_script(script))

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_raw(self, result: SearchResult) -> RawScript:
        raise NotImplementedError
