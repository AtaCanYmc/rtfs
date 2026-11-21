# Roadmap

## v0.1.0 (Current)

- [x] Canonical Pydantic v2 strict AST (`ScriptDocument`, `Scene`, `Action`, `Dialogue`, `Transition`).
- [x] Async HTTP client with per-host rate-limiting and exponential backoff retries.
- [x] SQLite-backed local disk caching in `~/.cache/rtfs`.
- [x] Coordinate-clustering PDF screenplay parser via PyMuPDF.
- [x] Indentation and `<b>`-tag HTML screenplay parser via Selectolax Lexbor.
- [x] Plain-text and HTML fallback transcript parser.
- [x] Parallel multi-provider search (`imsdb`, `scriptslug`, `tvwriting`, `subslikescript`) with `rapidfuzz` ranking.
- [x] JSON, Fountain, plain-text, and character/scene analytics exporters.
- [x] Typer + Rich CLI (`rtfs search`, `rtfs get`, `rtfs stats`).

## v0.2.0

- [ ] Dual-column simultaneous dialogue detection in `PdfScreenplayParser` via horizontal bounding-box overlap (`y0` intersection with separate `x0` columns).
- [ ] Interactive terminal prompt (`rtfs get --interactive`) to select from ranked search candidates before downloading.
- [ ] Scene-level filtering in `rtfs get` (`--character`, `--location`, `--scene-range`).
- [ ] Local file parsing support (`rtfs parse ./local_script.pdf --format json`) without provider lookup.

## v0.3.0

- [ ] Final Draft (`.fdx`) XML parser and exporter.
- [ ] Batch export command (`rtfs batch queries.txt --output-dir ./corpus`) with concurrency limits.
