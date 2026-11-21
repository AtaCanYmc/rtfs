# Changelog

## [0.1.1](https://github.com/AtaCanYmc/rtfs/compare/v0.1.0...v0.1.1) (2026-11-21)


### Features

* add logo SVG and update README with logo and description ([2f9e13f](https://github.com/AtaCanYmc/rtfs/commit/2f9e13f61cc0153efaeb27d4d65dd146ef072cc3))
* add Makefile, changelog, and release configuration files ([a9d5579](https://github.com/AtaCanYmc/rtfs/commit/a9d55793127620bb0882b32b949d940fe48e9dce))
* implement caching mechanism with multiple backends and update related components ([a105a6a](https://github.com/AtaCanYmc/rtfs/commit/a105a6aa7c15e024641022a80cb80c7cb0211dbc))
* **mcp:** add FastMCP server implementation with screenplay tools and CLI command ([633b7ef](https://github.com/AtaCanYmc/rtfs/commit/633b7ef4325bf77cb166e256d5e77153db205a31))
* rename package from rtfs to pyrtfs and update installation instructions ([b8b3253](https://github.com/AtaCanYmc/rtfs/commit/b8b3253b8eb7017f0b8db5ca14a0170d4e924a9f))
* update project metadata in pyproject.toml and release-please.yml ([6c1a14b](https://github.com/AtaCanYmc/rtfs/commit/6c1a14b583b602fd8166f1608b07503b33049311))


### Bug Fixes

* **security:** enforce SSRF/redirect guards, provider host allowlists, PDF page cap, and 0700 cache dir ([62bfe0e](https://github.com/AtaCanYmc/rtfs/commit/62bfe0e7abd4c62089302ae226b9a28f5ed465ea))


### Documentation

* **roadmap:** update v0.1.0 completed cache and security items and upcoming milestones ([4ab6471](https://github.com/AtaCanYmc/rtfs/commit/4ab6471d3854f1ac83afcdc23feba9fa4ea56efd))

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
