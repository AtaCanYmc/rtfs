# Changelog

## 0.1.0 (2026-11-21)

### Features

* Canonical Pydantic v2 strict AST (`ScriptDocument`, `Scene`, `Action`, `Dialogue`, `Transition`).
* Coordinate-clustering PDF screenplay parser via PyMuPDF (`PdfScreenplayParser`).
* Indentation and `<b>`-tag HTML screenplay parser via Selectolax Lexbor (`HtmlScreenplayParser`).
* Plain-text and HTML fallback transcript parser (`TranscriptParser`).
* Parallel multi-provider search (`imsdb`, `scriptslug`, `tvwriting`, `subslikescript`) with `rapidfuzz` ranking.
* Pluggable async `CacheBackend` layer (`disk://`, `redis://`, `rediss://`, `memory://`, `none://`).
* Progressive-disclosure FastMCP server (`rtfs mcp`) with bounded scene range and dialogue filtering tools.
* JSON, Fountain, plain-text, and character/scene analytics exporters.
* Typer + Rich CLI (`rtfs search`, `rtfs get`, `rtfs stats`, `rtfs mcp`).

### Security

* SSRF and redirect target validation in `HttpClient` blocking loopback, private, and link-local hosts.
* Provider domain allowlists (`BaseProvider.resolve_allowed_url`) and bounded PDF page iteration (`max_pages=500`).
* Restrictive `0700` permissions on local disk cache directory creation.
