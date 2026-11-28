---
name: rtfs
description: "Fetch, parse, diff, and analyze movie and TV screenplays via the rtfs CLI, Python SDK, or FastMCP server."
---

# rtfs

Use `rtfs` to search, fetch, parse, diff, and export movie and TV screenplays into structured JSON AST, JSONL, Fountain, or Final Draft (`.fdx`).

## When to Use

- Searching for a movie or TV screenplay across IMSDb, ScriptSlug, TVWriting, or SubsLikeScript.
- Parsing local `.pdf`, `.fdx`, `.fountain`, `.html`, or `.txt` scripts into structured scenes, dialogue, and action.
- Streaming `.jsonl` records for NLP/ML datasets or comparing two script drafts with `rtfs diff`.
- Querying bounded-context screenplay scenes via the FastMCP server (`rtfs mcp`).

## Prerequisites & Installation

Before running any `rtfs` command, verify it is available (`which rtfs` or `rtfs --version`). If `rtfs` is **not** installed on the device, **ask the user for confirmation before installing**, and offer the preferred method:

- `uv tool install "pyrtfs[all]"` (recommended)
- `pipx install "pyrtfs[all]"`
- `pip install "pyrtfs[all]"`
- `brew install AtaCanYmc/tap/rtfs`

## CLI Quick Reference

```bash
# Search across providers
rtfs search "Interstellar"

# Fetch and export to JSON, Fountain, FDX, or JSONL
rtfs get "Interstellar" --format json --output interstellar.json
rtfs get "Succession" --character "KENDALL" --scene-range "1-10"

# Parse a local file offline
rtfs parse ./script.fountain --format fdx --output ./script.fdx
rtfs parse ./script.pdf --format jsonl --output ./corpus.jsonl

# Compare two drafts (scene headings and normalized dialogue)
rtfs diff draft_v1.fountain draft_v2.fdx

# Compute scene and character statistics
rtfs stats "Interstellar"

# Print ScriptDocument JSON Schema
rtfs schema

# Start FastMCP server (stdio) or optional HTTP API (requires pyrtfs[api])
rtfs mcp --transport stdio
rtfs serve --host 127.0.0.1 --port 8000
```

## Python SDK

```python
import asyncio
from rtfs.core.client import RTFSClient

async def main() -> None:
    async with RTFSClient() as client:
        doc = await client.get_document("Arrival")
        print(doc.metadata.title, len(doc.scenes))

asyncio.run(main())
```

## MCP Resources & Tools

- **Tools**: `search_scripts`, `get_script_overview`, `get_scenes`, `search_dialogue`, `get_script_stats`.
- **Resources**:
  - `rtfs://script/{source}/{slug}/fountain`
  - `rtfs://script/{source}/{slug}/scenes/{offset}/{limit}`
