# rtfs Documentation

[Back to root README](../README.md)

## Reference Guides

| Guide | Scope |
| :--- | :--- |
| [Core Architecture](core.md) | `RTFSClient`, `ScriptAggregator`, Pydantic v2 AST models, caching, and SSRF/DNS-pinning security. |
| [Parsers](parsers.md) | `PdfScreenplayParser` (dual-column & OCR hook), `FdxParser`, `FountainParser`, `HtmlScreenplayParser`, and `TranscriptParser`. |
| [OCR & Scanned PDFs](ocr.md) | `ScannedPdfError`, `pyrtfs[ocr]` (`tesseract_ocr_hook`), `rtfs parse --ocr`, and custom OCR hooks. |
| [Providers](providers.md) | Built-in sources (`imsdb`, `scriptslug`, `tvwriting`, `subslikescript`) and `rtfs.providers` entry-point plugins. |
| [Plugin Developer Kit](plugin-kit.md) | Single-file `BaseProvider` template and 15-minute `rtfs.providers` guide. |
| [Exporters](exporters.md) | JSON, streaming JSONL, Fountain, Final Draft (`.fdx`), plain text, and character-normalized analytics. |
| [CLI & MCP](cli-and-mcp.md) | Typer CLI commands (`search`, `get`, `parse`, `diff`, `batch`, `stats`, `schema`, `serve`, `mcp`) and FastMCP tools/resources. |
| [HTTP API Server](api.md) | Optional `pyrtfs[api]` FastAPI server (`rtfs serve`), endpoints, and deployment. |
| [AI Agent Skill & MCP](skills.md) | `npx skills` installation, manual skill symlinks, and `claude_desktop_config.json` setup. |
| [Recipes](recipes.md) | Copy-paste workflows for ML/NLP JSONL corpora, OCR hooks, draft diffing, and custom provider plugins. |
| [Examples](examples.md) | Verified CLI command runs and outputs for JSONL, FDX conversion, and `rtfs diff`. |
| [Live Web Playground](playground.html) | 100% client-side Pyodide WASM playground for `.fountain`, `.fdx`, and `.txt` scripts. |
| [Use Cases & Best Practices](use-cases.md) | Recommended architectures, LLM context bounding, caching, and corpus tips. |
