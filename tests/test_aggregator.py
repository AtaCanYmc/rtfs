from __future__ import annotations

from pathlib import Path

from rtfs.core.aggregator import ScriptAggregator
from rtfs.core.cache import ScriptCache
from rtfs.core.http import HttpClient
from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider


class FakeWorkingProvider(BaseProvider):
    def __init__(
        self,
        name: str,
        fmt: str,
        results: list[SearchResult],
        raw: RawScript,
        http: HttpClient,
    ) -> None:
        super().__init__(http)
        self.name = name
        self.format = fmt  # type: ignore[assignment]
        self._results = results
        self._raw = raw

    async def search(self, query: str) -> list[SearchResult]:
        return self._results

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        return self._raw


class FakeFailingProvider(BaseProvider):
    name = "broken"

    async def search(self, query: str) -> list[SearchResult]:
        raise RuntimeError("Upstream provider rate-limited (429)")

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        raise RuntimeError("Cannot fetch")


async def test_aggregator_resilience_and_priority_ranking(tmp_path: Path) -> None:
    http = HttpClient()
    cache = ScriptCache(cache_dir=tmp_path / "cache")

    dummy_raw = RawScript(
        content="<pre>INT. ROOM - DAY\n\n                    NEO\n          Hello.</pre>",
        content_type="html",
        metadata=ScriptMetadata(
            title="The Matrix",
            year=1999,
            media_type="movie",
            source="imsdb",
            format="screenplay",
            url="https://imsdb.com/scripts/Matrix,-The.html",
        ),
    )

    imsdb_provider = FakeWorkingProvider(
        name="imsdb",
        fmt="screenplay",
        results=[
            SearchResult(
                title="The Matrix",
                url="https://imsdb.com/scripts/Matrix,-The.html",
                source="imsdb",
                media_type="movie",
                format="screenplay",
            )
        ],
        raw=dummy_raw,
        http=http,
    )

    scriptslug_provider = FakeWorkingProvider(
        name="scriptslug",
        fmt="screenplay",
        results=[
            SearchResult(
                title="The Matrix",
                url="https://www.scriptslug.com/script/the-matrix-1999",
                source="scriptslug",
                media_type="movie",
                format="screenplay",
                year=1999,
            )
        ],
        raw=dummy_raw,
        http=http,
    )

    transcript_provider = FakeWorkingProvider(
        name="subslikescript",
        fmt="transcript",
        results=[
            SearchResult(
                title="The Matrix",
                url="https://subslikescript.com/movie/The_Matrix-133093",
                source="subslikescript",
                media_type="movie",
                format="transcript",
                year=1999,
            )
        ],
        raw=dummy_raw,
        http=http,
    )

    agg = ScriptAggregator(
        http=http,
        cache=cache,
        providers={
            "imsdb": imsdb_provider,
            "scriptslug": scriptslug_provider,
            "tvwriting": FakeFailingProvider(http),
            "subslikescript": transcript_provider,
        },
    )

    # Default search excludes subslikescript and survives tvwriting raising an exception
    results = await agg.search("The Matrix", allow_transcript=False)
    assert len(results) == 2
    # PDF screenplay provider (scriptslug) ranks above HTML screenplay provider (imsdb)
    assert results[0].source == "scriptslug"
    assert results[1].source == "imsdb"

    # Enabling allow_transcript includes subslikescript ranked after screenplay sources
    results_with_transcript = await agg.search("The Matrix", allow_transcript=True)
    assert len(results_with_transcript) == 3
    assert results_with_transcript[-1].source == "subslikescript"

    # End-to-end get() parses into ScriptDocument
    doc = await agg.get("The Matrix")
    assert doc.metadata.title == "The Matrix"
    assert len(doc.scenes) == 1

    await agg.close()
    cache.close()
