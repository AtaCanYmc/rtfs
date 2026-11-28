from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rtfs.core.aggregator import (
    ScriptAggregator,
    filter_scenes,
    parse_file,
    parse_scene_range,
)
from rtfs.core.cache import CacheBackend, CacheInfo, create_cache
from rtfs.core.models import ScriptDocument, SearchResult
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.exporters.fountain_exp import export_fountain, export_txt
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.stats_exp import ScriptStats, compute_stats

VALID_EXPORT_FORMATS = {"json", "fountain", "txt", "fdx"}
FORMAT_EXTENSIONS = {
    "json": ".json",
    "fountain": ".fountain",
    "txt": ".txt",
    "fdx": ".fdx",
}
SLUG_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass
class BatchItemResult:
    query: str
    ok: bool
    detail: str


def render_document(doc: ScriptDocument, fmt: str = "fountain") -> str:
    """Export a ScriptDocument into the requested text/XML/JSON format."""
    fmt_lower = fmt.lower().strip()
    if fmt_lower not in VALID_EXPORT_FORMATS:
        raise ValueError(
            f"Invalid format '{fmt}'. Choose from: json, fountain, txt, fdx"
        )
    if fmt_lower == "json":
        return export_json(doc)
    if fmt_lower == "fountain":
        return export_fountain(doc)
    if fmt_lower == "fdx":
        return export_fdx(doc)
    return export_txt(doc)


def read_batch_queries(queries_file: str | Path) -> list[str]:
    """Read non-empty, non-comment query lines from a batch input file."""
    path = Path(queries_file)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Queries file not found: {path}")
    queries: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        queries.append(stripped)
    if not queries:
        raise ValueError(f"No valid queries found in {path}")
    return queries


def sanitize_filename_slug(raw: str, index: int) -> str:
    slug = SLUG_SANITIZE_RE.sub("-", raw.strip().lower()).strip(".-_")
    return (slug or f"script-{index}")[:80]


class RTFSClient:
    """High-level async SDK & CLI service layer for searching, parsing, filtering, and exporting."""

    def __init__(
        self,
        cache: CacheBackend | str | None = None,
        aggregator: ScriptAggregator | None = None,
    ) -> None:
        self._owns_aggregator = aggregator is None
        self.aggregator = aggregator or ScriptAggregator(cache=cache)

    async def search(
        self,
        query: str,
        *,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> list[SearchResult]:
        return await self.aggregator.search(
            query,
            source=source,
            allow_transcript=allow_transcript,
        )

    async def search_with_fallback(
        self,
        query: str,
        *,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> list[SearchResult]:
        results = await self.search(
            query,
            source=source,
            allow_transcript=allow_transcript,
        )
        if not results and not allow_transcript and source == "all":
            results = await self.search(query, source="all", allow_transcript=True)
        return results

    async def get_document(
        self,
        query_or_url: str,
        *,
        source: str = "all",
        allow_transcript: bool = False,
        selected_result: SearchResult | None = None,
        character: str | None = None,
        location: str | None = None,
        scene_range: str | tuple[int, int] | None = None,
    ) -> ScriptDocument:
        if isinstance(scene_range, str) and scene_range.strip():
            parse_scene_range(scene_range)

        if selected_result is not None:
            doc = await self.aggregator.fetch_and_parse(selected_result)
        else:
            doc = await self.aggregator.get(
                query_or_url,
                source=source,
                allow_transcript=allow_transcript,
            )

        return filter_scenes(
            doc,
            character=character,
            location=location,
            scene_range=scene_range,
        )

    def parse_local(
        self,
        file_path: str | Path,
        *,
        title: str | None = None,
        content_type: Literal["html", "pdf", "text", "fdx", "fountain"] | None = None,
        character: str | None = None,
        location: str | None = None,
        scene_range: str | tuple[int, int] | None = None,
    ) -> ScriptDocument:
        if isinstance(scene_range, str) and scene_range.strip():
            parse_scene_range(scene_range)
        doc = parse_file(file_path, title=title, content_type=content_type)
        return filter_scenes(
            doc,
            character=character,
            location=location,
            scene_range=scene_range,
        )

    async def stats(
        self,
        query_or_url: str,
        *,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> ScriptStats:
        doc = await self.aggregator.get(
            query_or_url,
            source=source,
            allow_transcript=allow_transcript,
        )
        return compute_stats(doc)

    async def batch_export(
        self,
        queries_file: str | Path,
        output_dir: str | Path,
        *,
        fmt: str = "fountain",
        concurrency: int = 3,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> list[BatchItemResult]:
        fmt_lower = fmt.lower().strip()
        if fmt_lower not in VALID_EXPORT_FORMATS:
            raise ValueError("Invalid format. Choose from: json, fountain, txt, fdx")
        if concurrency < 1:
            raise ValueError("Concurrency must be >= 1")

        out_path = Path(output_dir)
        queries = read_batch_queries(queries_file)
        out_path.mkdir(parents=True, exist_ok=True)
        ext = FORMAT_EXTENSIONS[fmt_lower]

        sem = asyncio.Semaphore(concurrency)
        used_filenames: set[str] = set()
        filename_lock = asyncio.Lock()

        async def _process_one(idx: int, query: str) -> BatchItemResult:
            async with sem:
                try:
                    doc = await self.aggregator.get(
                        query,
                        source=source,
                        allow_transcript=allow_transcript,
                    )
                    rendered = render_document(doc, fmt_lower)
                    base_slug = sanitize_filename_slug(doc.metadata.title or query, idx)
                    async with filename_lock:
                        candidate_name = f"{base_slug}{ext}"
                        if candidate_name in used_filenames:
                            candidate_name = f"{base_slug}-{idx}{ext}"
                        used_filenames.add(candidate_name)

                    dest = (out_path / candidate_name).resolve()
                    if out_path.resolve() not in dest.parents:
                        raise ValueError(f"Unsafe output path resolved: {dest}")
                    dest.write_text(rendered, encoding="utf-8")
                    return BatchItemResult(query=query, ok=True, detail=str(dest))
                except Exception as exc:
                    return BatchItemResult(query=query, ok=False, detail=str(exc))

        return list(
            await asyncio.gather(
                *[_process_one(i, q) for i, q in enumerate(queries, start=1)]
            )
        )

    @staticmethod
    async def inspect_cache(cache_url: str | None = None) -> CacheInfo:
        cache = create_cache(cache_url)
        try:
            return await cache.info()
        finally:
            await cache.close()

    @staticmethod
    async def clear_cache(cache_url: str | None = None) -> CacheInfo:
        cache = create_cache(cache_url)
        try:
            info_before = await cache.info()
            await cache.clear()
            return info_before
        finally:
            await cache.close()

    async def close(self) -> None:
        if self._owns_aggregator:
            await self.aggregator.close()

    async def __aenter__(self) -> RTFSClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
