# Providers Module (`rtfs.providers`)

[← Back to Documentation Index](README.md)

This guide covers `rtfs.providers.base`, `rtfs.providers.imsdb`, `rtfs.providers.scriptslug`, `rtfs.providers.tvwriting`, and `rtfs.providers.subslikescript`.

## Table of Contents

- [1. Provider Architecture & Security Boundaries](#1-provider-architecture--security-boundaries)
- [2. Using Individual Providers Directly](#2-using-individual-providers-directly)
- [3. Title Normalization & Fuzzy Similarity](#3-title-normalization--fuzzy-similarity)
- [4. Writing a Custom Provider](#4-writing-a-custom-provider)

## 1. Provider Architecture & Security Boundaries

Every provider subclasses `BaseProvider` and implements two async methods:

- `async def search(self, query: str) -> list[SearchResult]`
- `async def fetch_raw(self, result: SearchResult) -> RawScript`

Each provider declares a class-level `allowed_hosts: ClassVar[set[str]]` set and resolves scraped `<a href>` attributes through `self.resolve_allowed_url(base_url, href)`. Any cross-origin link or non-public IP embedded in upstream HTML is discarded before `HttpClient` issues a request.

| Provider Class | `name` | `content_type` | `allowed_hosts` |
| :--- | :--- | :--- | :--- |
| `ScriptSlugProvider` | `scriptslug` | `pdf` | `{"scriptslug.com"}` |
| `TVWritingProvider` | `tvwriting` | `pdf` | `{"sites.google.com", "drive.google.com", "docs.google.com"}` |
| `IMSDbProvider` | `imsdb` | `html` | `{"imsdb.com"}` |
| `SubsLikeScriptProvider` | `subslikescript` | `text` | `{"subslikescript.com"}` |

## 2. Using Individual Providers Directly

```python
import asyncio
from rtfs.core.cache import MemoryCacheBackend
from rtfs.core.http import HttpClient
from rtfs.providers.imsdb import IMSDbProvider
from rtfs.providers.scriptslug import ScriptSlugProvider
from rtfs.providers.subslikescript import SubsLikeScriptProvider
from rtfs.providers.tvwriting import TVWritingProvider


async def main() -> None:
    cache = MemoryCacheBackend()
    async with HttpClient() as http:
        # 1. Script Slug (PDF movie & TV screenplays via sitemap-scripts.xml)
        slug_provider = ScriptSlugProvider(http, cache)
        slug_hits = await slug_provider.search("Arrival")
        if slug_hits:
            raw_pdf = await slug_provider.fetch_raw(slug_hits[0])
            print(f"ScriptSlug PDF bytes: {len(raw_pdf.content)} from {raw_pdf.metadata.url}")

        # 2. IMSDb (HTML movie screenplays)
        imsdb_provider = IMSDbProvider(http, cache)
        imsdb_hits = await imsdb_provider.search("The Matrix")
        if imsdb_hits:
            raw_html = await imsdb_provider.fetch_raw(imsdb_hits[0])
            print(f"IMSDb writers: {raw_html.metadata.writers}")

        # 3. TV Writing (PDF TV pilots and episode scripts)
        tv_provider = TVWritingProvider(http, cache)
        tv_hits = await tv_provider.search("Breaking Bad")
        print(f"TVWriting matches: {len(tv_hits)}")

        # 4. SubsLikeScript (Fallback dialogue transcripts)
        subs_provider = SubsLikeScriptProvider(http, cache)
        subs_hits = await subs_provider.search("Chernobyl")
        print(f"SubsLikeScript matches: {len(subs_hits)}")

    await cache.close()


asyncio.run(main())
```

## 3. Title Normalization & Fuzzy Similarity

`rtfs.providers.base` exports `normalize_title_for_match` and `compute_title_similarity` to handle inverted articles (`"Matrix, The"`) and prevent false-positive `WRatio` matches on common stopwords like `"the"`.

```python
from rtfs.providers.base import compute_title_similarity, normalize_title_for_match

assert normalize_title_for_match("Matrix, The") == "matrix"
assert normalize_title_for_match("The Grand Budapest Hotel") == "grand budapest hotel"

# Exact match after normalization scores 100.0
assert compute_title_similarity("The Matrix", "Matrix, The") == 100.0

# Sequels score high but below exact title match
sequel_score = compute_title_similarity("The Matrix", "The Matrix Reloaded")
assert 80.0 < sequel_score < 100.0

# Unrelated titles sharing only "The" do not get boosted
unrelated_score = compute_title_similarity("The Matrix", "The Honourable Woman")
assert unrelated_score < 45.0
```

## 4. Writing a Custom Provider

You can register custom internal or archival screenplay repositories into `ScriptAggregator`:

```python
import asyncio
from typing import ClassVar
from rtfs.core.aggregator import ScriptAggregator
from rtfs.core.http import HttpClient
from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider, compute_title_similarity


class CustomFdxArchiveProvider(BaseProvider):
    name = "custom_archive"
    format = "screenplay"
    BASE_URL = "https://scripts.example.org"
    allowed_hosts: ClassVar[set[str]] = {"scripts.example.org"}

    async def search(self, query: str) -> list[SearchResult]:
        cached = await self._get_cached_search(query)
        if cached is not None:
            return cached

        # Example static or fetched catalog
        catalog = [("Inception", 2010, "/fdx/inception-2010.fdx")]
        results: list[SearchResult] = []
        for title, year, path in catalog:
            score = compute_title_similarity(query, title)
            url = self.resolve_allowed_url(self.BASE_URL, path)
            if score >= 50.0 and url:
                results.append(
                    SearchResult(
                        title=title,
                        year=year,
                        url=url,
                        source=self.name,
                        media_type="movie",
                        format="screenplay",
                        score=score,
                    )
                )
        await self._set_cached_search(query, results)
        return results

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        cached = await self._get_cached_raw(result.url)
        if cached is not None:
            return cached

        xml_text = await self.http.get_text(result.url)
        raw = RawScript(
            content=xml_text,
            content_type="fdx",
            metadata=ScriptMetadata(
                title=result.title,
                year=result.year,
                media_type=result.media_type,
                source=self.name,
                format="screenplay",
                url=result.url,
            ),
        )
        await self._set_cached_raw(result.url, raw)
        return raw


async def main() -> None:
    http = HttpClient()
    custom_provider = CustomFdxArchiveProvider(http)
    async with ScriptAggregator(
        http=http,
        cache="memory://",
        providers={"custom_archive": custom_provider},
    ) as agg:
        hits = await agg.search("Inception")
        print(hits)


asyncio.run(main())
```
