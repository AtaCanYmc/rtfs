from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from rtfs.core.cache import ScriptCache
from rtfs.core.http import HttpClient
from rtfs.core.models import RawScript, SearchResult


class BaseProvider(ABC):
    name: str = "base"
    format: Literal["screenplay", "transcript"] = "screenplay"

    def __init__(self, http: HttpClient, cache: ScriptCache | None = None) -> None:
        self.http = http
        self.cache = cache

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_raw(self, result: SearchResult) -> RawScript:
        raise NotImplementedError
