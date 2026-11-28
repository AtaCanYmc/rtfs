# CLI & FastMCP Server (`rtfs.cli` & `rtfs.mcp`)

[← Back to Documentation Index](README.md)

This guide covers `rtfs.cli.main` and `rtfs.mcp.server`.

## Table of Contents

- [1. CLI Cookbook (`rtfs.cli.main`)](#1-cli-cookbook-rtfsclimain)
- [2. Programmatic FastMCP Server & `MCPService` (`rtfs.mcp.server`)](#2-programmatic-fastmcp-server--mcpservice-rtfsmcpserver)

## 1. CLI Cookbook (`rtfs.cli.main`)

### Search Providers (`rtfs search`)

```bash
# Search all screenplay providers (Script Slug, TV Writing, IMSDb)
rtfs search "The Matrix"

# Restrict to a single provider
rtfs search "Breaking Bad" --source tvwriting

# Include fallback subtitle transcripts from SubsLikeScript
rtfs search "Chernobyl" --allow-transcript
```

### Fetch, Filter & Export (`rtfs get`)

```bash
# Export to Fountain, JSON, plain text, or Final Draft (.fdx)
rtfs get "The Matrix" --format fountain --output matrix.fountain
rtfs get "The Matrix" --format json --output matrix.json
rtfs get "The Matrix" --format fdx --output matrix.fdx

# Interactive prompt: view ranked table on stderr and pick candidate index
rtfs get "The Matrix" --interactive --format fountain

# Scene-level filtering (AND combination of character, location, and 1-indexed scene range)
rtfs get "The Matrix" \
  --character "MORPHEUS" \
  --location "NEBUCHADNEZZAR" \
  --scene-range "1-40" \
  --format fountain
```

### Offline Local File Parsing (`rtfs parse`)

```bash
# Parse a local PDF, FDX, HTML, or TXT screenplay without network calls
rtfs parse ./shooting_script.pdf --format fdx --output shooting_script.fdx
rtfs parse ./draft.fdx --format json --character "TRINITY" --scene-range "1-10"
```

### Concurrent Batch Export (`rtfs batch`)

Create a `queries.txt` file (`#` comments and blank lines are skipped):

```text
# Sci-Fi Corpus
The Matrix
Arrival
https://imsdb.com/scripts/Inception.html
```

Run batch export with bounded concurrency:

```bash
rtfs batch queries.txt --output-dir ./corpus --format json --concurrency 3
```

### Cache Management (`rtfs cache`)

```bash
# Inspect active cache backend, location, entry count, and byte size
rtfs cache info
rtfs cache info --format json
rtfs cache info --cache-url "redis://localhost:6379/0"

# Clear all cached entries
rtfs cache clear
rtfs cache clear --cache-url "disk:///tmp/rtfs-cache"
```

### Script Analytics (`rtfs stats`)

```bash
rtfs stats "The Matrix"
```

### Start the FastMCP Server (`rtfs mcp`)

```bash
# Default stdio transport for Claude Desktop, Cursor, and Claude Code
rtfs mcp --transport stdio

# SSE transport on a custom port with Redis caching
rtfs mcp --transport sse --host 127.0.0.1 --port 8000 --cache-url "redis://localhost:6379/0"
```

## 2. Programmatic FastMCP Server & `MCPService` (`rtfs.mcp.server`)

`MCPService` provides progressive-disclosure screenplay exploration for AI agents and caches parsed `ScriptDocument` ASTs both in-process and in the configured `CacheBackend` so sequential tool calls never re-download or re-parse the same script.

```python
import asyncio
from rtfs.core.aggregator import ScriptAggregator
from rtfs.mcp.server import (
    MCPService,
    get_scenes,
    get_script_overview,
    get_script_stats,
    search_dialogue,
    search_scripts,
)


async def main() -> None:
    agg = ScriptAggregator(cache="memory://")
    service = MCPService(aggregator=agg)

    # 1. Search available scripts
    hits = await search_scripts("The Matrix", limit=5, service=service)
    print("Search hits:", len(hits))

    # 2. Fetch compact structural overview (metadata, top 15 characters, full scene_index)
    overview = await get_script_overview("The Matrix", service=service)
    print(f"Total scenes: {overview['total_scenes']}")
    print("First 3 scenes:", overview["scene_index"][:3])

    # 3. Fetch a bounded range of scenes (hard-capped at MAX_SCENE_RANGE = 10 scenes per call)
    fountain_slice = await get_scenes(
        "The Matrix",
        start_scene=1,
        end_scene=3,
        format="fountain",
        service=service,
    )
    print(fountain_slice[:300])

    # Export a scene slice as Final Draft .fdx XML or JSON
    fdx_slice = await get_scenes(
        "The Matrix",
        start_scene=1,
        end_scene=2,
        format="fdx",
        service=service,
    )
    assert "<FinalDraft" in str(fdx_slice)

    # 4. Filter dialogue turns by character name and/or keyword
    lines = await search_dialogue(
        "The Matrix",
        character="MORPHEUS",
        keyword="real",
        limit=10,
        service=service,
    )
    for turn in lines:
        print(f"[Scene {turn['scene_number']}] {turn['character']}: {turn['lines']}")

    # 5. Compute full scene and character statistics
    stats = await get_script_stats("The Matrix", service=service)
    print("INT/EXT ratio:", stats["int_ext_ratio"])

    await service.close()


asyncio.run(main())
```

## Semantic Scene Search (`search_scenes_semantic`)

Install the optional semantic extra (`fastembed`):

```bash
pip install "pyrtfs[semantic]"
```

The FastMCP server exposes `search_scenes_semantic(query_or_url, query, top_k=5)` (capped at 10 scenes per call) to retrieve conceptually matching scenes without loading the full script into context.

## Interactive Terminal Viewer (`rtfs view`)

Install the optional TUI extra (`textual`):

```bash
pip install "pyrtfs[tui]"
```

Browse scenes with the keyboard, highlight a specific character's dialogue, and optionally inspect a side-by-side diff:

```bash
rtfs view ./draft_v1.fountain --character ALICE --diff ./draft_v2.fdx
```

## FastMCP Tool & Resource Examples

```python
from rtfs.mcp.server import create_mcp_server

mcp = create_mcp_server(cache_url="disk://~/.cache/rtfs")
```

Example tool calls from an MCP client:

```json
{
  "tool": "get_script_overview",
  "arguments": { "query_or_url": "The Matrix" }
}
```

```json
{
  "tool": "search_scenes_semantic",
  "arguments": {
    "query_or_url": "The Matrix",
    "query": "training simulation fight",
    "top_k": 5
  }
}
```

```json
{
  "tool": "diff_scripts",
  "arguments": {
    "query_or_url_a": "scriptslug:dune-2021",
    "query_or_url_b": "imsdb:Dune"
  }
}
```

Example resource URIs:

- `rtfs://script/scriptslug/the-matrix-1999/fountain`
- `rtfs://script/scriptslug/the-matrix-1999/scenes/0/10`
- `rtfs://script/scriptslug/the-matrix-1999/stats`

## Environment Diagnostics (`rtfs doctor`)

Inspect Python version, `RTFS_CACHE_URL`, installed optional extras (`mcp`, `redis`, `api`, `ocr`, `semantic`, `tui`), and `tesseract` binary availability:

```bash
rtfs doctor
```

## MCP Registry (`server.json`)

The repository includes [`server.json`](../server.json) (`io.github.atacanymc/rtfs`) for one-click discovery in the official MCP Registry, Smithery, and Glama (`uvx pyrtfs mcp`).
