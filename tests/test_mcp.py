from __future__ import annotations

import sys

import pytest

from rtfs.core.aggregator import ScriptAggregator
from rtfs.core.cache import MemoryCacheBackend
from rtfs.core.http import HttpClient
from rtfs.core.models import (
    RawScript,
    ScriptMetadata,
    SearchResult,
)
from rtfs.mcp.server import (
    MAX_SCENE_RANGE,
    MCPService,
    create_mcp_server,
    get_scenes,
    get_script_overview,
    get_script_stats,
    search_dialogue,
    search_scripts,
)
from rtfs.providers.base import BaseProvider


class _MockMatrixProvider(BaseProvider):
    name = "scriptslug"
    format = "screenplay"

    def __init__(self, http: HttpClient, cache: MemoryCacheBackend) -> None:
        super().__init__(http, cache)
        self.fetch_count = 0

    async def search(self, query: str) -> list[SearchResult]:
        return [
            SearchResult(
                title="The Matrix",
                year=1999,
                media_type="movie",
                source="scriptslug",
                format="screenplay",
                url="https://www.scriptslug.com/script/the-matrix-1999",
                score=100.0,
            ),
            SearchResult(
                title="The Matrix Reloaded",
                year=2003,
                media_type="movie",
                source="scriptslug",
                format="screenplay",
                url="https://www.scriptslug.com/script/the-matrix-reloaded-2003",
                score=90.0,
            ),
        ]

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        self.fetch_count += 1
        # Build a 12-scene HTML fixture to test progressive disclosure and 10-scene cap
        scenes_html: list[str] = ["<pre>"]
        for idx in range(1, 13):
            loc_prefix = "INT." if idx % 2 == 1 else "EXT."
            scenes_html.append(f"<b>{loc_prefix} LOCATION {idx} - NIGHT</b>\n")
            scenes_html.append(f"Action in scene {idx}.\n")
            scenes_html.append("                    <b>MORPHEUS</b>\n")
            scenes_html.append(f"          Welcome to scene {idx}, Neo. Take the red pill.\n")
            scenes_html.append("                    <b>NEO (V.O.)</b>\n")
            scenes_html.append("              (whispering)\n")
            scenes_html.append(f"          Whoa in scene {idx}.\n")
        scenes_html.append("</pre>")

        return RawScript(
            content="\n".join(scenes_html),
            content_type="html",
            metadata=ScriptMetadata(
                title="The Matrix",
                year=1999,
                media_type="movie",
                writers=["Lilly Wachowski", "Lana Wachowski"],
                source="scriptslug",
                format="screenplay",
                url=result.url,
            ),
        )


def _build_test_service() -> tuple[MCPService, _MockMatrixProvider]:
    http = HttpClient()
    cache = MemoryCacheBackend()
    provider = _MockMatrixProvider(http, cache)
    agg = ScriptAggregator(
        http=http,
        cache=cache,
        providers={"scriptslug": provider},
    )
    return MCPService(aggregator=agg), provider


async def test_mcp_missing_dependency_raises_helpful_importerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "mcp", None)
    monkeypatch.setitem(sys.modules, "mcp.server", None)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", None)

    with pytest.raises(
        ImportError,
        match=r"MCP server requires the mcp extra: pip install pyrtfs\[mcp\]",
    ):
        create_mcp_server(cache="memory://")


async def test_mcp_search_scripts() -> None:
    service, _ = _build_test_service()
    results = await search_scripts("Matrix", limit=1, service=service)
    assert len(results) == 1
    assert results[0]["title"] == "The Matrix"
    assert results[0]["year"] == 1999
    assert results[0]["source"] == "scriptslug"
    await service.close()


async def test_mcp_get_script_overview_and_ast_caching() -> None:
    service, provider = _build_test_service()
    overview = await get_script_overview("The Matrix", service=service)

    assert overview["metadata"]["title"] == "The Matrix"
    assert overview["total_scenes"] == 12
    assert len(overview["scene_index"]) == 12
    assert overview["scene_index"][0] == {
        "scene_number": 1,
        "heading": "INT. LOCATION 1 - NIGHT",
    }
    assert len(overview["top_characters"]) == 2
    assert overview["top_characters"][0]["character"] in {"MORPHEUS", "NEO"}
    # Ensure full dialogue lines are NOT dumped in overview
    assert "red pill" not in str(overview)

    # Subsequent tool call reuses cached parsed AST without re-fetching from provider
    assert provider.fetch_count == 1
    scene_text = await get_scenes("The Matrix", start_scene=1, end_scene=2, service=service)
    assert provider.fetch_count == 1
    assert isinstance(scene_text, str)
    assert "INT. LOCATION 1 - NIGHT" in scene_text
    assert "EXT. LOCATION 2 - NIGHT" in scene_text
    assert "LOCATION 3" not in scene_text

    await service.close()


async def test_mcp_get_scenes_range_cap_and_json_format() -> None:
    service, _ = _build_test_service()

    # Requesting > 10 scenes raises a descriptive ValueError
    with pytest.raises(ValueError, match=f"maximum of {MAX_SCENE_RANGE} scenes"):
        await get_scenes("The Matrix", start_scene=1, end_scene=11, service=service)

    # Requesting invalid range raises ValueError
    with pytest.raises(ValueError, match="Invalid scene range"):
        await get_scenes("The Matrix", start_scene=5, end_scene=3, service=service)

    # JSON format returns structured scene objects
    payload = await get_scenes(
        "The Matrix",
        start_scene=3,
        end_scene=4,
        format="json",
        service=service,
    )
    assert isinstance(payload, dict)
    assert payload["start_scene"] == 3
    assert payload["end_scene"] == 4
    assert payload["total_scenes_in_script"] == 12
    assert len(payload["scenes"]) == 2

    await service.close()


async def test_mcp_search_dialogue_filtering() -> None:
    service, _ = _build_test_service()

    # Requires at least one of character or keyword
    with pytest.raises(ValueError, match="At least one of 'character' or 'keyword'"):
        await search_dialogue("The Matrix", service=service)

    # Filter by character (case-insensitive)
    neo_lines = await search_dialogue("The Matrix", character="neo", limit=5, service=service)
    assert len(neo_lines) == 5
    assert all(item["character"] == "NEO" for item in neo_lines)
    assert neo_lines[0]["parenthetical"] == "whispering"
    assert neo_lines[0]["modifiers"] == ["V.O."]

    # Filter by keyword (case-insensitive)
    pill_lines = await search_dialogue(
        "The Matrix",
        keyword="RED PILL",
        limit=3,
        service=service,
    )
    assert len(pill_lines) == 3
    assert all(item["character"] == "MORPHEUS" for item in pill_lines)

    # Filter by both character and keyword for specific scene
    scene_7_line = await search_dialogue(
        "The Matrix",
        character="morpheus",
        keyword="scene 7",
        service=service,
    )
    assert len(scene_7_line) == 1
    assert scene_7_line[0]["scene_number"] == 7

    await service.close()


async def test_mcp_get_script_stats_and_resource() -> None:
    service, _ = _build_test_service()
    stats = await get_script_stats("The Matrix", service=service)

    assert stats["title"] == "The Matrix"
    assert stats["total_scenes"] == 12
    assert stats["int_scenes"] == 6
    assert stats["ext_scenes"] == 6
    assert stats["int_ext_ratio"] == 1.0

    fountain_res = await service.get_full_fountain_resource("scriptslug", "the-matrix")
    assert "Title: The Matrix" in fountain_res
    assert "INT. LOCATION 1 - NIGHT" in fountain_res

    await service.close()
