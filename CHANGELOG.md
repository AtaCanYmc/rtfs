# Changelog

## [0.1.3](https://github.com/AtaCanYmc/rtfs/compare/v0.1.2...v0.1.3) (2026-11-28)


### Features

* **cli:** add --version/-V, schema, serve, and jsonl export format ([c5d6c4c](https://github.com/AtaCanYmc/rtfs/commit/c5d6c4cf754fda7cbac173262c8920ed4d37ac3e))
* implement v0.4.0 (FountainParser, scanned PDF OCR hook, character normalization, rtfs diff) ([19d06a7](https://github.com/AtaCanYmc/rtfs/commit/19d06a7636be3d7869304827342d974ae3a2c346))
* implement v0.5.0 (JSONL exporter, entry-point providers, MCP pagination, mypy CI, pyrtfs[api]) ([afa1cf1](https://github.com/AtaCanYmc/rtfs/commit/afa1cf14cb58ff3f16614b2e530db394433d87a4))
* **pages:** add dark/light mode and SEO/AEO metadata (robots.txt, sitemap.xml, llms.txt, JSON-LD) ([b3afa84](https://github.com/AtaCanYmc/rtfs/commit/b3afa8401080d73c2c24d006a8e77453f10f5fb8))
* **pages:** add npx skills install tab to hero bar ([c04e36e](https://github.com/AtaCanYmc/rtfs/commit/c04e36ee7fba36b38341be284114c0be19200661))
* **pages:** add SVG favicon, webmanifest, and theme-color meta ([503c8fc](https://github.com/AtaCanYmc/rtfs/commit/503c8fcd0954879e481cd4e77c37575530840486))
* **pages:** showcase v0.5.0 CLI diff, MCP scene pagination, and pyrtfs[api] ([2d300be](https://github.com/AtaCanYmc/rtfs/commit/2d300be3fae6cd18486c19578f20b88afbfb8be9))


### Documentation

* add api.md, recipes.md, and update docs index ([7fc9513](https://github.com/AtaCanYmc/rtfs/commit/7fc95131bf16ac4f69f9a2eab17705c5ccc83a15))
* add cache, batch, mcp, and serve CLI examples ([0f10aff](https://github.com/AtaCanYmc/rtfs/commit/0f10aff816b2b4775514c5e9fc89c8825edc0fcc))
* add live filtered Fountain and JSONL get examples ([f49057d](https://github.com/AtaCanYmc/rtfs/commit/f49057d370cb39e9450616a703c9a5f7ad31c7de))
* add live search and stats examples with real data ([b68f8b0](https://github.com/AtaCanYmc/rtfs/commit/b68f8b0b26ff3189abbf44ec71f39da383f59e22))
* add use-cases.md with usage patterns and best practices ([8a8ce74](https://github.com/AtaCanYmc/rtfs/commit/8a8ce74c6cda215b344cbf590c72f01ee8ecfb09))
* add verified CLI examples in docs/examples.md ([690c1f2](https://github.com/AtaCanYmc/rtfs/commit/690c1f261966e59007acce85a4a58fb1063a8854))
* expand examples.md with rtfs schema and character-normalized stats ([9494f4d](https://github.com/AtaCanYmc/rtfs/commit/9494f4d77693b77e8d9fd3cc8f9746ff738cfa2f))
* **readme:** add codecov badge, v0.4.0/v0.5.0 overview, and new docs links ([7a44438](https://github.com/AtaCanYmc/rtfs/commit/7a444385f06573274127b2e0b4a5e5f95a29ff24))
* **skills:** add AI agent skill folder (skills/rtfs/SKILL.md) and setup guide ([7ca4f0e](https://github.com/AtaCanYmc/rtfs/commit/7ca4f0ee163da3cff5c484ba62f60127988907fc))
* **skills:** prompt user before installing rtfs if missing ([1c51527](https://github.com/AtaCanYmc/rtfs/commit/1c51527b3def0af066965c92aff466c064f09b31))
* upgrade architecture diagrams to branded SVG ([a121582](https://github.com/AtaCanYmc/rtfs/commit/a1215822386fe83edd213c94df4f4c758506affb))

## [0.1.2](https://github.com/AtaCanYmc/rtfs/compare/v0.1.1...v0.1.2) (2026-11-21)


### Features

* implement v0.2.0 and v0.3.0 features (dual-column PDF dialogue, FDX parser/exporter, DNS pinning, parse/cache/batch CLI, interactive & scene filtering) ([aac2b2c](https://github.com/AtaCanYmc/rtfs/commit/aac2b2cbbca66e685a7c1a752435029173e50ebc))
* **pages:** add interactive release hub site to GitHub Pages (docs/index.html) ([2af7b4d](https://github.com/AtaCanYmc/rtfs/commit/2af7b4d69f4bd81f64fcdfb2e0e1693b84397b56))


### Bug Fixes

* **pages:** remediate hallmark, antislop-ui, and modern-web-guidance audit findings ([ec9121d](https://github.com/AtaCanYmc/rtfs/commit/ec9121d7f8eddbbd291b4968d490f9a9c264ddcf))
* **search:** strip leading articles in fuzzy ranking, query scriptslug sitemap, and use import pymupdf ([8fce05c](https://github.com/AtaCanYmc/rtfs/commit/8fce05c9ac6a6c6eb0aae3c25dc0df49afc24929))
* **security:** replace URL substring checks with strict hostname suffix matching (CodeQL [#1](https://github.com/AtaCanYmc/rtfs/issues/1)-[#5](https://github.com/AtaCanYmc/rtfs/issues/5)) ([6888fc1](https://github.com/AtaCanYmc/rtfs/commit/6888fc1c2d0f0925a9a117fe0b185f60985b20e6))


### Code Refactoring

* decompose pdf_screenplay into parsers/pdf/, extract RTFSClient & cli/formatting, and split core/network from core/http ([e09bc82](https://github.com/AtaCanYmc/rtfs/commit/e09bc820b97b4f7afed65dbdfa340dd519a46c60))


### Documentation

* add detailed module examples and guides under docs/ ([f33b655](https://github.com/AtaCanYmc/rtfs/commit/f33b655b65ba93a88dfcd68ea9ee6e4bc0095c79))
* **readme:** add Homebrew tap badge ([43c4816](https://github.com/AtaCanYmc/rtfs/commit/43c48167171477b4cbdf3bfcdec016d7a1c080e9))
* **readme:** add PyPI badge and Homebrew tap installation instructions ([e725d39](https://github.com/AtaCanYmc/rtfs/commit/e725d393c81667c2c925f4ae2dc5f192049b4e04))

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
