# Core Modules: Models, HTTP, Cache & Aggregator

[← Back to Documentation Index](README.md)

This guide covers `rtfs.core.models`, `rtfs.core.http`, `rtfs.core.cache`, and `rtfs.core.aggregator`.

## Table of Contents

- [1. Canonical AST Models (`rtfs.core.models`)](#1-canonical-ast-models-rtfscoremodels)
- [2. DNS-Pinned Async HTTP Client (`rtfs.core.http`)](#2-dns-pinned-async-http-client-rtfscorehttp)
- [3. Pluggable Cache Layer (`rtfs.core.cache`)](#3-pluggable-cache-layer-rtfscorecache)
- [4. Aggregator, Scene Filtering & Local Parsing (`rtfs.core.aggregator`)](#4-aggregator-scene-filtering--local-parsing-rtfscoreaggregator)

## 1. Canonical AST Models (`rtfs.core.models`)

All data structures in `rtfs.core.models` use Pydantic v2 with `ConfigDict(strict=True)`. Every parser outputs a `ScriptDocument` containing `ScriptMetadata` and an ordered list of `Scene` objects.

```python
from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    SearchResult,
    Transition,
)

# 1. Construct ScriptMetadata
metadata = ScriptMetadata(
    title="The Matrix",
    year=1999,
    media_type="movie",
    writers=["Lilly Wachowski", "Lana Wachowski"],
    source="scriptslug",
    format="screenplay",
    url="https://www.scriptslug.com/script/the-matrix-1999",
)

# 2. Build a Scene with Action, simultaneous Dual Dialogue, and a Transition
scene = Scene(
    scene_number=1,
    heading="INT. NEBUCHADNEZZAR DECK - NIGHT",
    location="NEBUCHADNEZZAR DECK",
    time_of_day="NIGHT",
    elements=[
        Action(text="Monitors flicker across the steel deck."),
        Dialogue(
            character="TRINITY",
            modifiers=["O.S."],
            parenthetical="urgent",
            lines="Watch the door!",
            dual=False,
        ),
        Dialogue(
            character="NEO",
            modifiers=[],
            parenthetical=None,
            lines="I have the key!",
            dual=True,  # Marks simultaneous right-column dialogue paired with TRINITY
        ),
        Transition(text="CUT TO:"),
    ],
)

# 3. Assemble and serialize ScriptDocument
doc = ScriptDocument(metadata=metadata, scenes=[scene])
json_str = doc.model_dump_json(indent=2)
restored = ScriptDocument.model_validate_json(json_str)
assert restored == doc

# 4. RawScript wraps unparsed provider payloads ("html" | "pdf" | "text" | "fdx")
raw = RawScript(
    content="<pre>INT. ROOM - DAY\n\nAction.</pre>",
    content_type="html",
    metadata=metadata,
)

# 5. SearchResult represents a ranked search hit from a provider
hit = SearchResult(
    title="The Matrix",
    year=1999,
    url="https://www.scriptslug.com/script/the-matrix-1999",
    source="scriptslug",
    media_type="movie",
    format="screenplay",
    score=112.0,
)
```

## 2. DNS-Pinned Async HTTP Client (`rtfs.core.http`)

`HttpClient` provides per-host rate limiting, exponential backoff retries, response size limits (`max_response_bytes`), manual redirect validation, and time-of-check to time-of-use (TOCTOU) DNS rebinding protection via `PinnedAsyncNetworkBackend`.

```python
import asyncio
import ipaddress
import socket
from rtfs.core.http import (
    HttpClient,
    host_matches,
    is_public_ip,
    validate_public_http_url,
)


async def main() -> None:
    # 1. URL & IP boundary helpers
    assert is_public_ip(ipaddress.ip_address("93.184.216.34")) is True
    assert is_public_ip(ipaddress.ip_address("100.64.0.1")) is False  # Blocks CGNAT
    assert is_public_ip(ipaddress.ip_address("::ffff:127.0.0.1")) is False  # Blocks IPv4-mapped loopback

    validate_public_http_url("https://imsdb.com/scripts/Matrix,-The.html")
    assert host_matches("assets.scriptslug.com", "scriptslug.com") is True
    assert host_matches("evil-scriptslug.com", "scriptslug.com") is False

    # 2. Standard usage with context manager
    async with HttpClient(
        timeout=15.0,
        max_retries=3,
        min_interval=0.25,
        max_redirects=5,
        max_response_bytes=25 * 1024 * 1024,
    ) as http:
        html_text = await http.get_text("https://imsdb.com/all-scripts.html")
        print(f"Fetched {len(html_text)} chars")

    # 3. Injecting a custom deterministic DNS resolver for offline testing
    async def custom_resolver(
        host: str,
        port: int,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    client_with_pinning = HttpClient(resolver=custom_resolver)
    await client_with_pinning.close()


asyncio.run(main())
```

## 3. Pluggable Cache Layer (`rtfs.core.cache`)

`rtfs.core.cache` defines the async `CacheBackend` protocol (`get`, `set`, `delete`, `clear`, `info`, `close`) operating strictly on `bytes`.

```python
import asyncio
from pathlib import Path
from rtfs.core.cache import (
    CacheBackend,
    CacheInfo,
    DiskCacheBackend,
    MemoryCacheBackend,
    NullCacheBackend,
    create_cache,
    make_cache_key,
)


async def main() -> None:
    # 1. Create cache from URI ("disk://...", "redis://...", "memory://", "none://")
    cache = create_cache("memory://")

    key = make_cache_key("raw:imsdb", "https://imsdb.com/scripts/Matrix,-The.html")
    await cache.set(key, b"raw-html-bytes", ttl=3600)

    hit = await cache.get(key)
    assert hit == b"raw-html-bytes"

    # 2. Inspect cache metadata (backend, location, entries, size_bytes)
    info: CacheInfo = await cache.info()
    print(f"Backend={info.backend}, Entries={info.entries}, Bytes={info.size_bytes}")

    # 3. Clear and close
    await cache.clear()
    await cache.close()

    # 4. Direct DiskCacheBackend usage (creates directory with 0o700 permissions)
    disk = DiskCacheBackend(Path("/tmp/rtfs-example-cache"), default_ttl=86400)
    await disk.set("k1", b"payload")
    print(await disk.info())
    await disk.clear()
    await disk.close()

    # 5. Custom CacheBackend implementation
    class DictCache:
        def __init__(self) -> None:
            self.data: dict[str, bytes] = {}

        async def get(self, key: str) -> bytes | None:
            return self.data.get(key)

        async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
            self.data[key] = value

        async def delete(self, key: str) -> None:
            self.data.pop(key, None)

        async def clear(self) -> None:
            self.data.clear()

        async def info(self) -> CacheInfo:
            return CacheInfo(
                backend="custom",
                location=None,
                entries=len(self.data),
                size_bytes=sum(len(v) for v in self.data.values()),
            )

        async def close(self) -> None:
            self.data.clear()

    custom = DictCache()
    assert isinstance(custom, CacheBackend)


asyncio.run(main())
```

## 4. Aggregator, Scene Filtering & Local Parsing (`rtfs.core.aggregator`)

`ScriptAggregator` coordinates parallel searches across providers, fetches raw payloads, and delegates to the appropriate parser. The module also exposes `filter_scenes`, `parse_scene_range`, and `parse_file`.

```python
import asyncio
from pathlib import Path
from rtfs.core.aggregator import (
    ScriptAggregator,
    filter_scenes,
    parse_file,
    parse_scene_range,
)


async def main() -> None:
    # 1. Parallel search and fetch across providers
    async with ScriptAggregator(cache="memory://") as agg:
        results = await agg.search("The Matrix", source="all", allow_transcript=False)
        for item in results[:3]:
            print(f"{item.title} ({item.year}) [{item.source}] score={item.score}")

        doc = await agg.get("The Matrix")

    # 2. Scene-level filtering (AND combination of character, location, and 1-indexed scene_range)
    start, end = parse_scene_range("1-25")
    filtered = filter_scenes(
        doc,
        character="MORPHEUS",
        location="NEBUCHADNEZZAR",
        scene_range=(start, end),
    )
    print(f"Filtered from {len(doc.scenes)} scenes down to {len(filtered.scenes)} scenes")

    # 3. Offline local file parsing (.pdf, .fdx, .html, .txt) without provider lookups
    local_fdx = Path("sample.fdx")
    local_fdx.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<FinalDraft DocumentType="Script" Template="No" Version="5">\n'
        "  <Content>\n"
        '    <Paragraph Type="Scene Heading"><Text>INT. LAB - NIGHT</Text></Paragraph>\n'
        '    <Paragraph Type="Action"><Text>Servers hum quietly.</Text></Paragraph>\n'
        "  </Content>\n"
        "</FinalDraft>\n",
        encoding="utf-8",
    )
    local_doc = parse_file(local_fdx, title="Local Demo")
    print(f"Parsed local file: {local_doc.metadata.title} ({len(local_doc.scenes)} scene)")
    local_fdx.unlink()

    # 4. High-level RTFSClient SDK wrapper (search, filtered get, local parse, batch export, cache management)
    from rtfs import RTFSClient, render_document

    async with RTFSClient(cache="memory://") as client:
        doc_slice = await client.get_document(
            "The Matrix",
            character="NEO",
            scene_range="1-15",
        )
        fountain_text = render_document(doc_slice, "fountain")
        print(f"Rendered {len(fountain_text)} chars via RTFSClient")


asyncio.run(main())
```
