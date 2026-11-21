from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import ClassVar, Literal
from urllib.parse import urljoin, urlparse

from rapidfuzz import fuzz

from rtfs.core.cache import (
    CacheBackend,
    create_cache,
    decode_raw_script,
    decode_search_results,
    encode_raw_script,
    encode_search_results,
    make_cache_key,
)
from rtfs.core.http import HttpClient, host_matches, validate_public_http_url
from rtfs.core.models import RawScript, SearchResult

STOPWORDS = {"the", "a", "an", "of", "and", "in", "on", "to", "for"}
TRAILING_ARTICLE_RE = re.compile(r"^(.*?),\s*(the|a|an)$", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")


def normalize_title_for_match(title: str) -> str:
    """Normalize script title by moving trailing ', The' and stripping leading articles."""
    cleaned = title.strip()
    m = TRAILING_ARTICLE_RE.match(cleaned)
    if m:
        cleaned = f"{m.group(2)} {m.group(1)}"
    lowered = NON_ALNUM_RE.sub(" ", cleaned.lower())
    tokens = lowered.split()
    if len(tokens) > 1 and tokens[0] in {"the", "a", "an"}:
        tokens = tokens[1:]
    return " ".join(tokens)


def compute_title_similarity(query: str, title: str) -> float:
    """Compute rapidfuzz similarity while preventing stopword-only false positives."""
    q_norm = normalize_title_for_match(query)
    t_norm = normalize_title_for_match(title)
    if not q_norm or not t_norm:
        return 0.0

    q_tokens = {tok for tok in q_norm.split() if tok not in STOPWORDS} or set(q_norm.split())
    t_tokens = {tok for tok in t_norm.split() if tok not in STOPWORDS} or set(t_norm.split())

    q_ratio = float(fuzz.QRatio(q_norm, t_norm))
    sort_ratio = float(fuzz.token_sort_ratio(q_norm, t_norm))

    # Only allow WRatio's partial/subset boost when meaningful tokens overlap
    has_token_overlap = bool(q_tokens & t_tokens) or (q_norm in t_norm) or (t_norm in q_norm)
    if has_token_overlap:
        w_ratio = float(fuzz.WRatio(q_norm, t_norm))
        # Penalize extra trailing words so "The Matrix" beats "The Matrix Reloaded"
        len_penalty = min(10.0, max(0, len(t_norm.split()) - len(q_norm.split())) * 4.0)
        return max(q_ratio, sort_ratio, w_ratio - len_penalty)

    return max(q_ratio, sort_ratio)


class BaseProvider(ABC):
    name: str = "base"
    format: Literal["screenplay", "transcript"] = "screenplay"
    allowed_hosts: ClassVar[set[str]] = set()

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

    def resolve_allowed_url(self, base_url: str, href: str) -> str | None:
        """Resolve a candidate href against base_url and ensure it belongs to allowed_hosts."""
        try:
            resolved = validate_public_http_url(urljoin(base_url, href))
        except ValueError:
            return None
        host = (urlparse(resolved).hostname or "").lower()
        if self.allowed_hosts and not host_matches(host, *self.allowed_hosts):
            return None
        return resolved

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
