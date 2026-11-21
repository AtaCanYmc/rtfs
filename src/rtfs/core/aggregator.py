from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from rtfs.core.cache import CacheBackend, create_cache
from rtfs.core.http import HttpClient, host_matches
from rtfs.core.models import (
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    SearchResult,
)
from rtfs.parsers.base import BaseParser
from rtfs.parsers.fdx import FdxParser
from rtfs.parsers.html_screenplay import HtmlScreenplayParser
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser
from rtfs.parsers.transcript import TranscriptParser
from rtfs.providers.base import BaseProvider, compute_title_similarity
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

SCENE_RANGE_RE = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*$")

EXTENSION_TO_CONTENT_TYPE: dict[str, Literal["html", "pdf", "text", "fdx"]] = {
    ".pdf": "pdf",
    ".fdx": "fdx",
    ".xml": "fdx",
    ".html": "html",
    ".htm": "html",
    ".txt": "text",
    ".fountain": "text",
}


def parse_scene_range(spec: str) -> tuple[int, int]:
    """Parse 'N' or 'start-end' into a 1-indexed inclusive (start, end) tuple."""
    m = SCENE_RANGE_RE.match(spec)
    if not m:
        raise ValueError(
            f"Invalid scene range '{spec}'. Expected a positive integer 'N' or range 'start-end'."
        )
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) is not None else start
    if start < 1 or end < start:
        raise ValueError(
            f"Invalid scene range '{spec}': scene numbers must be >= 1 and end >= start."
        )
    return start, end


def filter_scenes(
    doc: ScriptDocument,
    *,
    character: str | None = None,
    location: str | None = None,
    scene_range: str | tuple[int, int] | None = None,
) -> ScriptDocument:
    """Filter scenes in a ScriptDocument using logical AND across character, location, and range."""
    char_q = character.strip().lower() if character and character.strip() else None
    loc_q = location.strip().lower() if location and location.strip() else None

    bounds: tuple[int, int] | None = None
    if isinstance(scene_range, str) and scene_range.strip():
        bounds = parse_scene_range(scene_range)
    elif isinstance(scene_range, tuple):
        start, end = scene_range
        if start < 1 or end < start:
            raise ValueError(f"Invalid scene_range tuple: ({start}, {end})")
        bounds = (start, end)

    if char_q is None and loc_q is None and bounds is None:
        return doc

    matched: list[Scene] = []
    for scene in doc.scenes:
        if bounds is not None and not (bounds[0] <= scene.scene_number <= bounds[1]):
            continue

        if loc_q is not None:
            loc_target = f"{scene.location or ''} {scene.heading}".lower()
            if loc_q not in loc_target:
                continue

        if char_q is not None:
            has_char = any(
                isinstance(el, Dialogue) and char_q in el.character.lower()
                for el in scene.elements
            )
            if not has_char:
                continue

        matched.append(scene)

    return ScriptDocument(metadata=doc.metadata, scenes=matched)


def _build_default_parsers() -> dict[str, BaseParser]:
    return {
        "pdf": PdfScreenplayParser(),
        "html": HtmlScreenplayParser(),
        "text": TranscriptParser(),
        "fdx": FdxParser(),
    }


def parse_file(
    path: str | Path,
    *,
    title: str | None = None,
    content_type: Literal["html", "pdf", "text", "fdx"] | None = None,
    media_type: Literal["movie", "tv"] = "movie",
) -> ScriptDocument:
    """Parse a local screenplay/transcript file (.pdf, .fdx, .html, .txt) without network calls."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Local script file not found: {file_path}")

    resolved_type = content_type
    if resolved_type is None:
        ext = file_path.suffix.lower()
        resolved_type = EXTENSION_TO_CONTENT_TYPE.get(ext)
        if resolved_type is None:
            raise ValueError(
                f"Unsupported file extension '{ext}' for '{file_path.name}'. "
                f"Supported: {', '.join(sorted(EXTENSION_TO_CONTENT_TYPE))}"
            )

    parsers = _build_default_parsers()
    parser = parsers.get(resolved_type)
    if parser is None:
        raise ValueError(f"Unsupported content_type: {resolved_type}")

    raw_bytes = file_path.read_bytes()
    payload: bytes | str = (
        raw_bytes
        if resolved_type == "pdf"
        else raw_bytes.decode("utf-8", errors="replace")
    )

    stem_title = file_path.stem.replace("-", " ").replace("_", " ").strip()
    inferred_title = (
        title
        if title is not None
        else ("" if resolved_type == "fdx" else stem_title)
    )
    fmt: Literal["screenplay", "transcript"] = (
        "transcript" if resolved_type == "text" else "screenplay"
    )
    meta_title = (
        inferred_title
        if resolved_type == "fdx"
        else (inferred_title or file_path.stem)
    )
    meta = ScriptMetadata(
        title=meta_title,
        media_type=media_type,
        source="local",
        format=fmt,
        url=str(file_path.resolve()),
    )
    raw = RawScript(content=payload, content_type=resolved_type, metadata=meta)
    doc = parser.parse(raw)
    if not doc.metadata.title:
        doc = doc.model_copy(
            update={
                "metadata": doc.metadata.model_copy(
                    update={"title": stem_title or "Untitled"}
                )
            }
        )
    return doc


class ScriptAggregator:
    """Orchestrates parallel multi-provider searches, fetching, and AST parsing."""

    def __init__(
        self,
        http: HttpClient | None = None,
        cache: CacheBackend | str | None = None,
        providers: dict[str, BaseProvider] | None = None,
    ) -> None:
        self._owns_http = http is None
        self.http = http or HttpClient()
        self._owns_cache = cache is None or isinstance(cache, str)
        self.cache: CacheBackend = (
            create_cache(cache) if (cache is None or isinstance(cache, str)) else cache
        )
        self.providers: dict[str, BaseProvider] = providers or {
            "imsdb": IMSDbProvider(self.http, self.cache),
            "scriptslug": ScriptSlugProvider(self.http, self.cache),
            "tvwriting": TVWritingProvider(self.http, self.cache),
            "subslikescript": SubsLikeScriptProvider(self.http, self.cache),
        }
        self._parsers: dict[str, BaseParser] = _build_default_parsers()

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
                base_similarity = compute_title_similarity(query, item.title)
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
        host = (parsed.hostname or "").lower()
        path = parsed.path
        slug = path.rstrip("/").split("/")[-1] or "Direct Script"
        title = (
            slug.replace(".html", "")
            .replace(".pdf", "")
            .replace(".fdx", "")
            .replace("-", " ")
            .strip()
        )

        if host_matches(host, "imsdb.com"):
            source = "imsdb"
            fmt = "screenplay"
        elif host_matches(host, "scriptslug.com"):
            source = "scriptslug"
            fmt = "screenplay"
        elif host_matches(host, "sites.google.com", "drive.google.com", "docs.google.com"):
            source = "tvwriting"
            fmt = "screenplay"
        elif host_matches(host, "subslikescript.com"):
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

    def parse_file(
        self,
        path: str | Path,
        *,
        title: str | None = None,
        content_type: Literal["html", "pdf", "text", "fdx"] | None = None,
        media_type: Literal["movie", "tv"] = "movie",
    ) -> ScriptDocument:
        return parse_file(
            path,
            title=title,
            content_type=content_type,
            media_type=media_type,
        )

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
        await self.cache.close()

    async def __aenter__(self) -> ScriptAggregator:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
