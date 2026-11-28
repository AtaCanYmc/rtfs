from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from rtfs.core.aggregator import ScriptAggregator
from rtfs.core.cache import CacheBackend, make_cache_key
from rtfs.core.models import Dialogue, ScriptDocument
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.exporters.fountain_exp import export_fountain
from rtfs.exporters.stats_exp import compute_stats

MAX_SCENE_RANGE = 10


def _import_fastmcp() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "MCP server requires the mcp extra: pip install pyrtfs[mcp]"
        ) from exc
    return FastMCP


class MCPService:
    """Progressive-disclosure screenplay tools with parsed ScriptDocument caching."""

    def __init__(
        self,
        aggregator: ScriptAggregator | None = None,
        cache: CacheBackend | str | None = None,
    ) -> None:
        self._owns_aggregator = aggregator is None
        self.aggregator = aggregator or ScriptAggregator(cache=cache)
        # In-process parsed AST cache keyed by (query_or_url, source) so consecutive
        # tool calls (e.g. get_script_overview -> get_scenes) never re-parse.
        self._parsed_docs: dict[str, ScriptDocument] = {}

    async def _resolve_document(
        self,
        query_or_url: str,
        source: str | None = None,
    ) -> ScriptDocument:
        effective_source = source or "all"
        doc_key = make_cache_key(f"ast:{effective_source}", query_or_url.strip().lower())

        if doc_key in self._parsed_docs:
            return self._parsed_docs[doc_key]

        cached_ast = await self.aggregator.cache.get(doc_key)
        if cached_ast is not None:
            doc = ScriptDocument.model_validate_json(cached_ast.decode("utf-8"))
            self._parsed_docs[doc_key] = doc
            return doc

        doc = await self.aggregator.get(query_or_url, source=effective_source)
        await self.aggregator.cache.set(
            doc_key,
            doc.model_dump_json().encode("utf-8"),
        )
        self._parsed_docs[doc_key] = doc
        return doc

    async def search_scripts(
        self,
        query: str,
        allow_transcript: bool = False,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        capped = max(1, min(limit, 50))
        results = await self.aggregator.search(
            query,
            source="all",
            allow_transcript=allow_transcript,
        )
        return [
            {
                "title": r.title,
                "year": r.year,
                "media_type": r.media_type,
                "source": r.source,
                "format": r.format,
                "url": r.url,
            }
            for r in results[:capped]
        ]

    async def get_script_overview(
        self,
        query_or_url: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        doc = await self._resolve_document(query_or_url, source=source)
        stats = compute_stats(doc, top_n=15)
        meta = doc.metadata
        return {
            "metadata": {
                "title": meta.title,
                "year": meta.year,
                "media_type": meta.media_type,
                "writers": meta.writers,
                "source": meta.source,
                "format": meta.format,
                "url": meta.url,
            },
            "total_scenes": len(doc.scenes),
            "top_characters": [
                {
                    "character": c.character,
                    "dialogue_turns": c.dialogue_turns,
                    "word_count": c.word_count,
                }
                for c in stats.top_characters
            ],
            "scene_index": [
                {
                    "scene_number": s.scene_number,
                    "heading": s.heading,
                }
                for s in doc.scenes
            ],
        }

    async def get_scenes(
        self,
        query_or_url: str,
        start_scene: int,
        end_scene: int | None = None,
        format: Literal["fountain", "json", "fdx"] = "fountain",
    ) -> str | dict[str, Any]:
        target_end = start_scene if end_scene is None else end_scene
        if start_scene < 1 or target_end < start_scene:
            raise ValueError(
                f"Invalid scene range: start_scene={start_scene}, end_scene={target_end}. "
                "Scene numbers are 1-indexed and end_scene must be >= start_scene."
            )

        requested_count = target_end - start_scene + 1
        if requested_count > MAX_SCENE_RANGE:
            raise ValueError(
                f"Requested {requested_count} scenes ({start_scene}..{target_end}), "
                f"which exceeds the maximum of {MAX_SCENE_RANGE} scenes per call. "
                "Fetch a smaller range to protect context window limits."
            )

        doc = await self._resolve_document(query_or_url)
        total = len(doc.scenes)
        selected = [
            s for s in doc.scenes if start_scene <= s.scene_number <= target_end
        ]
        if not selected:
            raise ValueError(
                f"No scenes found in range {start_scene}..{target_end} "
                f"(script has {total} scenes)."
            )

        sliced_doc = ScriptDocument(metadata=doc.metadata, scenes=selected)
        if format == "json":
            return {
                "metadata": sliced_doc.metadata.model_dump(mode="json"),
                "start_scene": selected[0].scene_number,
                "end_scene": selected[-1].scene_number,
                "total_scenes_in_script": total,
                "scenes": [s.model_dump(mode="json") for s in selected],
            }
        if format == "fdx":
            return export_fdx(sliced_doc)
        return export_fountain(sliced_doc)

    async def search_dialogue(
        self,
        query_or_url: str,
        character: str | None = None,
        keyword: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        char_filter = (character or "").strip().lower()
        kw_filter = (keyword or "").strip().lower()
        if not char_filter and not kw_filter:
            raise ValueError(
                "At least one of 'character' or 'keyword' must be provided."
            )

        capped = max(1, min(limit, 100))
        doc = await self._resolve_document(query_or_url)
        matches: list[dict[str, Any]] = []

        for scene in doc.scenes:
            for elem in scene.elements:
                if not isinstance(elem, Dialogue):
                    continue
                if char_filter and char_filter not in elem.character.lower():
                    continue
                if kw_filter and kw_filter not in elem.lines.lower():
                    continue
                matches.append(
                    {
                        "scene_number": scene.scene_number,
                        "heading": scene.heading,
                        "character": elem.character,
                        "modifiers": elem.modifiers,
                        "parenthetical": elem.parenthetical,
                        "lines": elem.lines,
                    }
                )
                if len(matches) >= capped:
                    return matches

        return matches

    async def get_script_stats(self, query_or_url: str) -> dict[str, Any]:
        doc = await self._resolve_document(query_or_url)
        stats = compute_stats(doc, top_n=15)
        return asdict(stats)

    async def get_full_fountain_resource(self, source: str, slug: str) -> str:
        query = slug.replace("-", " ").strip()
        doc = await self._resolve_document(query, source=source)
        return export_fountain(doc)

    async def close(self) -> None:
        self._parsed_docs.clear()
        if self._owns_aggregator:
            await self.aggregator.close()


_default_service: MCPService | None = None


def _get_service(cache: CacheBackend | str | None = None) -> MCPService:
    global _default_service
    if _default_service is None:
        _default_service = MCPService(cache=cache)
    return _default_service


async def search_scripts(
    query: str,
    allow_transcript: bool = False,
    limit: int = 10,
    service: MCPService | None = None,
) -> list[dict[str, Any]]:
    """Search across active screenplay providers and return concise metadata."""
    svc = service or _get_service()
    return await svc.search_scripts(
        query=query,
        allow_transcript=allow_transcript,
        limit=limit,
    )


async def get_script_overview(
    query_or_url: str,
    source: str | None = None,
    service: MCPService | None = None,
) -> dict[str, Any]:
    """Fetch and parse a script, returning its structural map, top characters, and scene index."""
    svc = service or _get_service()
    return await svc.get_script_overview(query_or_url=query_or_url, source=source)


async def get_scenes(
    query_or_url: str,
    start_scene: int,
    end_scene: int | None = None,
    format: Literal["fountain", "json", "fdx"] = "fountain",
    service: MCPService | None = None,
) -> str | dict[str, Any]:
    """Return a single scene or inclusive scene range (max 10 scenes per call)."""
    svc = service or _get_service()
    return await svc.get_scenes(
        query_or_url=query_or_url,
        start_scene=start_scene,
        end_scene=end_scene,
        format=format,
    )


async def search_dialogue(
    query_or_url: str,
    character: str | None = None,
    keyword: str | None = None,
    limit: int = 30,
    service: MCPService | None = None,
) -> list[dict[str, Any]]:
    """Filter dialogue turns in a script by character name and/or keyword."""
    svc = service or _get_service()
    return await svc.search_dialogue(
        query_or_url=query_or_url,
        character=character,
        keyword=keyword,
        limit=limit,
    )


async def get_script_stats(
    query_or_url: str,
    service: MCPService | None = None,
) -> dict[str, Any]:
    """Compute scene breakdown, INT/EXT ratio, dialogue-to-action ratio, and character stats."""
    svc = service or _get_service()
    return await svc.get_script_stats(query_or_url=query_or_url)


def create_mcp_server(
    cache: CacheBackend | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    service: MCPService | None = None,
) -> Any:
    """Create and configure the FastMCP server instance with tools and resources."""
    fastmcp_cls = _import_fastmcp()
    svc = service or MCPService(cache=cache)
    mcp = fastmcp_cls("rtfs", host=host, port=port)

    @mcp.tool()
    async def search_scripts(
        query: str,
        allow_transcript: bool = False,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search across screenplay providers and return concise metadata."""
        return await svc.search_scripts(
            query=query,
            allow_transcript=allow_transcript,
            limit=limit,
        )

    @mcp.tool()
    async def get_script_overview(
        query_or_url: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Return script metadata, total scenes, top 15 characters, and the scene heading index."""
        return await svc.get_script_overview(query_or_url=query_or_url, source=source)

    @mcp.tool()
    async def get_scenes(
        query_or_url: str,
        start_scene: int,
        end_scene: int | None = None,
        format: Literal["fountain", "json", "fdx"] = "fountain",
    ) -> str | dict[str, Any]:
        """Fetch a single scene or range of scenes (capped at 10 scenes per call)."""
        return await svc.get_scenes(
            query_or_url=query_or_url,
            start_scene=start_scene,
            end_scene=end_scene,
            format=format,
        )

    @mcp.tool()
    async def search_dialogue(
        query_or_url: str,
        character: str | None = None,
        keyword: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Search dialogue lines by character name, keyword, or both."""
        return await svc.search_dialogue(
            query_or_url=query_or_url,
            character=character,
            keyword=keyword,
            limit=limit,
        )

    @mcp.tool()
    async def get_script_stats(query_or_url: str) -> dict[str, Any]:
        """Compute scene counts, INT/EXT breakdown, dialogue/action ratio, and character stats."""
        return await svc.get_script_stats(query_or_url=query_or_url)

    @mcp.tool()
    async def search_scenes_semantic(
        query_or_url: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic scene search (e.g. 'argument in the rain'), capped at 10 scenes."""
        from rtfs.core.semantic import search_scenes_semantic as _semantic_search

        doc = await svc._resolve_document(query_or_url=query_or_url)
        return _semantic_search(doc, query, top_k=top_k)

    @mcp.resource("rtfs://script/{source}/{slug}/fountain")
    async def script_fountain_resource(source: str, slug: str) -> str:
        """Full Fountain screenplay text resource for a given provider source and slug."""
        return await svc.get_full_fountain_resource(source=source, slug=slug)

    @mcp.resource("rtfs://script/{source}/{slug}/scenes/{offset}/{limit}")
    async def script_scenes_chunk_resource(
        source: str,
        slug: str,
        offset: int,
        limit: int,
    ) -> str | dict[str, Any]:
        """Paginated scene chunk resource for bounded-context LLM workflows."""
        return await svc.get_scenes(
            query_or_url=f"{source}:{slug}",
            start_scene=max(1, offset + 1),
            end_scene=max(1, offset + limit),
        )

    return mcp


def run_mcp_server(
    transport: Literal["stdio", "sse"] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    cache_url: str | None = None,
) -> None:
    """Start the FastMCP server on stdio or sse without polluting stdout."""
    mcp = create_mcp_server(cache=cache_url, host=host, port=port)
    mcp.run(transport=transport)
