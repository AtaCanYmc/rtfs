# Roadmap

## v0.1.0

- [x] Canonical Pydantic v2 strict AST (`ScriptDocument`, `Scene`, `Action`, `Dialogue`, `Transition`).
- [x] Async HTTP client with per-host rate-limiting, exponential backoff retries, SSRF/redirect guards, and response payload limits.
- [x] Pluggable async `CacheBackend` protocol (`disk://`, `redis://`, `rediss://`, `memory://`, `none://`) configurable via `RTFS_CACHE_URL`, `--cache-url`, `--no-cache`, or SDK injection.
- [x] Provider host allowlists and bounded PDF page extraction (`max_pages=500`).
- [x] Coordinate-clustering PDF screenplay parser via PyMuPDF.
- [x] Indentation and `<b>`-tag HTML screenplay parser via Selectolax Lexbor.
- [x] Plain-text and HTML fallback transcript parser.
- [x] Parallel multi-provider search (`imsdb`, `scriptslug`, `tvwriting`, `subslikescript`) with `rapidfuzz` ranking.
- [x] JSON, Fountain, plain-text, and character/scene analytics exporters.
- [x] Progressive-disclosure FastMCP server (`rtfs mcp`).
- [x] Typer + Rich CLI (`rtfs search`, `rtfs get`, `rtfs stats`, `rtfs mcp`).

## v0.2.0

- [x] Dual-column simultaneous dialogue detection in `PdfScreenplayParser` via horizontal bounding-box overlap (`y0` intersection with separate `x0` columns) and Fountain `^` dual-dialogue export.
- [x] Interactive terminal prompt (`rtfs get --interactive`) to select from ranked search candidates before downloading.
- [x] Scene-level filtering in `rtfs get` and `rtfs parse` (`--character`, `--location`, `--scene-range`).
- [x] Local file parsing support (`rtfs parse ./local_script.pdf --format json`) without provider lookup.
- [x] CLI cache management subcommands (`rtfs cache clear`, `rtfs cache info`).

## v0.3.0 (Current)

- [x] Final Draft (`.fdx`) XML parser (`FdxParser`) and exporter (`export_fdx`) with `<DualDialogue>` support and XXE/entity-expansion hardening.
- [x] Batch export command (`rtfs batch queries.txt --output-dir ./corpus`) with `--concurrency` semaphore limits.
- [x] DNS resolution pinning in `HttpClient` (`PinnedAsyncNetworkBackend` / `PinnedAsyncHTTPTransport`) to defend against time-of-check to time-of-use (TOCTOU) DNS rebinding.

## v0.4.0 — Parser & Format Depth

- [ ] Fountain input parser (`FountainParser`) enabling round-trip `.fountain` to `.fdx` and `.json` conversion.
- [ ] Scanned/image-only PDF detection with structured diagnostics and an optional OCR hook.
- [ ] Character alias and parenthetical normalization (`V.O.`, `O.S.`, `CONT'D`) across `stats` and `--character` filters.
- [ ] Draft comparison command (`rtfs diff <script_a> <script_b>`) for scene-level and dialogue-level diffs.

## v0.5.0 — Corpus, SDK & MCP Maturity

- [ ] Streaming `JSONL` corpus exporter for large-scale NLP and ML ingestion pipelines.
- [ ] Entry-point provider registry (`rtfs.providers`) for third-party screenplay sources.
- [ ] MCP scene-chunk pagination and resource URIs for bounded-context LLM workflows.
- [ ] Strict static type-checking (`mypy` / `pyright`) enforced in CI with `py.typed` distribution.
- [ ] Optional HTTP/REST API server extra (`pyrtfs[api]`) for self-hosted microservice deployments.

## v1.0.0 — Production Stability

- [ ] Frozen `RTFSClient` SDK and `ScriptDocument` v1 schema with semantic versioning guarantees.
- [ ] Versioned `ScriptDocument` JSON Schema (`rtfs schema`) for downstream validation.
- [ ] Golden-file regression suite covering PDF, FDX, HTML, and Fountain edge cases.
