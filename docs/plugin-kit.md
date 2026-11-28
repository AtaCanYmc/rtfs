# Plugin Developer Kit (`rtfs.providers`)

[Back to docs index](README.md)

Add a new screenplay archive to `rtfs` in under 15 minutes using the `rtfs.providers` entry-point registry.

## 1. Implement `BaseProvider` (Single-File Template)

```python
from __future__ import annotations

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider, compute_title_similarity


class MyArchiveProvider(BaseProvider):
    name = "my_archive"
    supports_transcript = False
    allowed_hosts = ("myarchive.example.org",)

    async def search(self, query: str) -> list[SearchResult]:
        html = await self.http.get_text("https://myarchive.example.org/search", params={"q": query})
        # Parse links and score titles with compute_title_similarity(query, title)
        return [
            SearchResult(
                title=query,
                url="https://myarchive.example.org/scripts/example.fountain",
                source=self.name,
                media_type="movie",
                format="screenplay",
                score=compute_title_similarity(query, query),
            )
        ]

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        text = await self.http.get_text(result.url)
        return RawScript(
            content=text,
            content_type="fountain",
            metadata=ScriptMetadata(
                title=result.title,
                source=self.name,
                url=result.url,
            ),
        )
```

## 2. Register via `pyproject.toml`

```toml
[project.entry-points."rtfs.providers"]
my_archive = "my_package.provider:MyArchiveProvider"
```

Once installed (`pip install -e .`), `ScriptAggregator` discovers `my_archive` automatically:

```bash
rtfs search "Interstellar" --source my_archive
```
