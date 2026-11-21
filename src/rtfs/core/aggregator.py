from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from rapidfuzz import fuzz

from rtfs.core.cache import ScriptCache
from rtfs.core.http import HttpClient
from rtfs.core.models import RawScript, ScriptDocument, SearchResult
from rtfs.parsers.base import BaseParser
from rtfs.parsers.html_screenplay import HtmlScreenplayParser
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser
from rtfs.parsers.transcript import TranscriptParser
from rtfs.providers.base import BaseProvider
from rtfs.providers.imsdb import IMSDbProvider
from rtfs.providers.scriptslug import ScriptSlugProvider
from rtfs.providers.subslikescript import SubsLikeScriptProvider
from rtfs.providers.tvwriting import TVWritingProvider

SOURCE_PRIORITY_BONUS: dict[str, float] = {
    "scriptslug": 12.0,     # PDF screenplay
    "tvwriting": 12.0,      # PDF screenplay
    "imsdb": 7.0,           # HTML screenplay
    "subslikescript": 0.0,  # Fallback transcript
}


class ScriptAggregator:
    """Orchestrates parallel multi-provider searches, fetching, and AST parsing."""

    def __init__(
        self,
        http: HttpClient | None = None,
        cache: ScriptCache | None = None,
        providers: dict[str, BaseProvider] | None = None,
    ) -> None:
        self._owns_http = http is None
        self.http = http or HttpClient()
        self.cache = cache if cache is not None else ScriptCache()
        self.providers: dict[str, BaseProvider] = providers or {
            "imsdb": IMSDbProvider(self.http, self.cache),
            "scriptslug": ScriptSlugProvider(self.http, self.cache),
            "tvwriting": TVWritingProvider(self.http, self.cache),
            "subslikescript": SubsLikeScriptProvider(self.http, self.cache),
        }
        self._parsers: dict[str, BaseParser] = {
            "pdf": PdfScreenplayParser(),
            "html": HtmlScreenplayParser(),
            "text": TranscriptParser(),
        }

    def _select_providers(
        self,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> list[BaseProvider]:
        if source != "all":
            if source not in self.providers:
                raise ValueError(f"Unknown source '{source}'. Valid: {list(self.providers)}")
            return [self.providers[source]]

        selected: list[BaseProvider] = []
        for name, provider in self.providers.items():
            if name == "subslikescript" and not allow_transcript:
                continue
            selected.append(provider)
        return selected

    async def search(
        self,
        query: str,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> list[SearchResult]:
        active_providers = self._select_providers(source, allow_transcript)
        tasks = [p.search(query) for p in active_providers]
        batches = await asyncio.gather(*tasks, return_exceptions=True)

        ranked: list[SearchResult] = []
        seen_urls: set[str] = set()

        for batch in batches:
            if isinstance(batch, BaseException):
                continue
            for item in batch:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                base_similarity = float(fuzz.WRatio(query.lower(), item.title.lower()))
                bonus = SOURCE_PRIORITY_BONUS.get(item.source, 0.0)
                ranked.append(item.model_copy(update={"score": round(base_similarity + bonus, 2)}))

        ranked.sort(
            key=lambda r: (
                r.score,
                SOURCE_PRIORITY_BONUS.get(r.source, 0.0),
            ),
            reverse=True,
        )
        return ranked

    def _result_from_url(self, url: str) -> SearchResult:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path
        slug = path.rstrip("/").split("/")[-1] or "Direct Script"
        title = slug.replace(".html", "").replace(".pdf", "").replace("-", " ").strip()

        if "imsdb.com" in host:
            source = "imsdb"
            fmt = "screenplay"
        elif "scriptslug.com" in host:
            source = "scriptslug"
            fmt = "screenplay"
        elif "tvwriting" in host or "sites.google.com" in host:
            source = "tvwriting"
            fmt = "screenplay"
        elif "subslikescript.com" in host:
            source = "subslikescript"
            fmt = "transcript"
        else:
            source = "scriptslug" if path.lower().endswith(".pdf") else "imsdb"
            fmt = "screenplay"

        return SearchResult(
            title=title or "Script",
            url=url,
            source=source,
            media_type="tv" if source == "tvwriting" else "movie",
            format=fmt,  # type: ignore[arg-type]
            score=100.0,
        )

    def parse_raw(self, raw: RawScript) -> ScriptDocument:
        parser = self._parsers.get(raw.content_type)
        if parser is None:
            raise ValueError(f"Unsupported content_type: {raw.content_type}")
        return parser.parse(raw)

    async def fetch_and_parse(self, result: SearchResult) -> ScriptDocument:
        provider = self.providers.get(result.source)
        if provider is None:
            raise ValueError(f"No provider registered for source '{result.source}'")
        raw = await provider.fetch_raw(result)
        return self.parse_raw(raw)

    async def get(
        self,
        query_or_url: str,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> ScriptDocument:
        if query_or_url.startswith(("http://", "https://")):
            result = self._result_from_url(query_or_url)
            return await self.fetch_and_parse(result)

        results = await self.search(
            query_or_url,
            source=source,
            allow_transcript=allow_transcript,
        )
        if not results and not allow_transcript and source == "all":
            results = await self.search(query_or_url, source="all", allow_transcript=True)

        if not results:
            raise LookupError(f"No scripts found matching '{query_or_url}'")

        last_err: Exception | None = None
        for candidate in results[:5]:
            try:
                return await self.fetch_and_parse(candidate)
            except Exception as exc:
                last_err = exc
                continue

        raise LookupError(
            f"Found matches for '{query_or_url}', but failed to fetch/parse: {last_err}"
        )

    async def close(self) -> None:
        if self._owns_http:
            await self.http.close()

    async def __aenter__(self) -> ScriptAggregator:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
