from __future__ import annotations

import asyncio
import fnmatch
import os
import socket
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock
from xml.sax.saxutils import escape

import anyio
import anyio.abc
import anyio.streams.tls
import httpx
import pymupdf as fitz
import pytest
from typer.testing import CliRunner

from rtfs.core.aggregator import ScriptAggregator
from rtfs.core.cache import CacheBackend
from rtfs.core.http import MAX_RESPONSE_BYTES, HttpClient
from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def sample_metadata() -> Callable[..., ScriptMetadata]:
    def _make(
        *,
        title: str = "The Matrix",
        year: int | None = 1999,
        media_type: Literal["movie", "tv"] = "movie",
        season: int | None = None,
        episode: int | None = None,
        writers: Sequence[str] | None = None,
        source: str = "scriptslug",
        fmt: Literal["screenplay", "transcript"] = "screenplay",
        url: str = "https://www.scriptslug.com/script/the-matrix-1999",
    ) -> ScriptMetadata:
        writer_list = (
            list(writers)
            if writers is not None
            else ["Lilly Wachowski", "Lana Wachowski"]
        )
        return ScriptMetadata(
            title=title,
            year=year,
            media_type=media_type,
            season=season,
            episode=episode,
            writers=writer_list,
            source=source,
            format=fmt,
            url=url,
        )

    return _make


@pytest.fixture
def make_pdf_bytes() -> Callable[..., bytes]:
    def _make(
        pages: list[list[tuple[float, float, str]]],
        *,
        fontsize: int = 11,
    ) -> bytes:
        doc = fitz.open()
        try:
            for page_lines in pages:
                page = doc.new_page(width=612, height=792)
                for x, y, text in page_lines:
                    page.insert_text((x, y), text, fontsize=fontsize)
            return doc.tobytes()
        finally:
            doc.close()

    return _make


@pytest.fixture
def make_dual_column_pdf_bytes(
    make_pdf_bytes: Callable[..., bytes],
) -> Callable[..., bytes]:
    def _make(
        *,
        heading: str = "INT. BUNKER - NIGHT",
        action: str | None = "Monitors flicker across the dark room.",
        regular_dialogue: tuple[str, str] | None = ("MORPHEUS", "Wait for my signal."),
        left_character: str = "TRINITY",
        left_lines: list[str] | None = None,
        left_parenthetical: str | None = None,
        right_character: str = "NEO",
        right_lines: list[str] | None = None,
        right_parenthetical: str | None = None,
        x_left: float = 108.0,
        x_right: float = 342.0,
        y_dual: float = 240.0,
        y_right_offset: float = 0.0,
        trailing_action: str | None = "Both move at once.",
    ) -> bytes:
        l_lines = left_lines if left_lines is not None else ["Watch the door!"]
        r_lines = right_lines if right_lines is not None else ["I have the key!"]

        items: list[tuple[float, float, str]] = [(72.0, 85.0, heading)]
        if action:
            items.append((72.0, 110.0, action))

        if regular_dialogue is not None:
            reg_char, reg_line = regular_dialogue
            items.append((216.0, 145.0, reg_char))
            items.append((144.0, 160.0, reg_line))

        y_l = y_dual
        items.append((x_left + 36.0, y_l, left_character))
        y_l += 14.0
        if left_parenthetical:
            items.append((x_left + 18.0, y_l, left_parenthetical))
            y_l += 14.0
        for line in l_lines:
            items.append((x_left, y_l, line))
            y_l += 14.0

        y_r = y_dual + y_right_offset
        items.append((x_right + 36.0, y_r, right_character))
        y_r += 14.0
        if right_parenthetical:
            items.append((x_right + 18.0, y_r, right_parenthetical))
            y_r += 14.0
        for line in r_lines:
            items.append((x_right, y_r, line))
            y_r += 14.0

        if trailing_action is not None:
            y_end = max(y_l, y_r) - 14.0
            y_trail = min(725.0, y_end + 32.0)
            items.append((72.0, y_trail, trailing_action))

        return make_pdf_bytes([items])

    return _make


def _fdx_dialogue_paragraphs(entry: Any) -> list[str]:
    if isinstance(entry, dict):
        character = str(entry["character"])
        modifiers = list(entry.get("modifiers") or [])
        parenthetical = entry.get("parenthetical")
        lines = entry.get("lines")
        runs = entry.get("runs")
    else:
        character, parenthetical, lines = entry
        modifiers = []
        runs = None

    mod_suffix = " ".join(f"({m})" for m in modifiers)
    cue = f"{character} {mod_suffix}".strip()
    out = [f'    <Paragraph Type="Character"><Text>{escape(cue)}</Text></Paragraph>']
    if parenthetical:
        paren_text = str(parenthetical).strip()
        if not (paren_text.startswith("(") and paren_text.endswith(")")):
            paren_text = f"({paren_text})"
        out.append(
            f'    <Paragraph Type="Parenthetical"><Text>{escape(paren_text)}</Text></Paragraph>'
        )

    if runs is not None:
        run_xml = "".join(
            (
                f'<Text Style="{escape(str(r.get("style", "")))}">'
                f'{escape(str(r["text"]))}</Text>'
                if isinstance(r, dict) and r.get("style")
                else f"<Text>{escape(str(r['text'] if isinstance(r, dict) else r))}</Text>"
            )
            for r in runs
        )
        out.append(f'    <Paragraph Type="Dialogue">{run_xml}</Paragraph>')
    else:
        lines_text = escape(str(lines or ""))
        out.append(f'    <Paragraph Type="Dialogue"><Text>{lines_text}</Text></Paragraph>')
    return out


@pytest.fixture
def make_fdx_xml() -> Callable[..., str]:
    def _make(
        *,
        scenes: list[dict[str, Any]] | None = None,
        include_dual: bool = False,
        version: str = "5",
    ) -> str:
        if scenes is None:
            default_elements: list[dict[str, Any]] = [
                {"type": "action", "text": "Rain streaks down the glass."},
                {
                    "type": "dialogue",
                    "character": "MORPHEUS",
                    "modifiers": ["V.O."],
                    "parenthetical": "calmly",
                    "runs": [{"text": "Free ", "style": "Bold"}, {"text": "your mind."}],
                },
            ]
            if include_dual:
                default_elements.append(
                    {
                        "type": "dual_dialogue",
                        "left": {
                            "character": "TRINITY",
                            "parenthetical": "urgent",
                            "lines": "Watch the door!",
                        },
                        "right": {
                            "character": "NEO",
                            "parenthetical": "focused",
                            "lines": "I see them.",
                        },
                    }
                )
            default_elements.append({"type": "transition", "text": "CUT TO:"})
            scenes_data: list[dict[str, Any]] = [
                {
                    "heading": "INT. BUNKER - NIGHT",
                    "elements": default_elements,
                },
                {
                    "heading": "EXT. ROOFTOP - DAWN",
                    "elements": [
                        {"type": "action", "text": "Sunlight breaks over the skyline."},
                        {"type": "dialogue", "character": "NEO", "lines": "It is done."},
                    ],
                },
            ]
        else:
            scenes_data = scenes

        paragraphs: list[str] = []
        for scene in scenes_data:
            heading = scene.get("heading")
            if heading:
                heading_xml = escape(str(heading))
                paragraphs.append(
                    f'    <Paragraph Type="Scene Heading"><Text>{heading_xml}</Text></Paragraph>'
                )

            if "elements" in scene:
                for elem in scene["elements"]:
                    etype = elem["type"]
                    if etype == "action":
                        act_xml = escape(str(elem["text"]))
                        paragraphs.append(
                            f'    <Paragraph Type="Action"><Text>{act_xml}</Text></Paragraph>'
                        )
                    elif etype == "transition":
                        trans_xml = escape(str(elem["text"]))
                        paragraphs.append(
                            f'    <Paragraph Type="Transition"><Text>{trans_xml}</Text></Paragraph>'
                        )
                    elif etype == "dialogue":
                        paragraphs.extend(_fdx_dialogue_paragraphs(elem))
                    elif etype == "dual_dialogue":
                        left_xml = "\n  ".join(_fdx_dialogue_paragraphs(elem["left"]))
                        right_xml = "\n  ".join(_fdx_dialogue_paragraphs(elem["right"]))
                        paragraphs.append(
                            "    <Paragraph>\n      <DualDialogue>\n"
                            f"  {left_xml}\n  {right_xml}\n"
                            "      </DualDialogue>\n    </Paragraph>"
                        )
            else:
                actions = scene.get("action")
                if isinstance(actions, str):
                    act_xml = escape(actions)
                    paragraphs.append(
                        f'    <Paragraph Type="Action"><Text>{act_xml}</Text></Paragraph>'
                    )
                elif isinstance(actions, list):
                    for act in actions:
                        act_xml = escape(str(act))
                        paragraphs.append(
                            f'    <Paragraph Type="Action"><Text>{act_xml}</Text></Paragraph>'
                        )

                for dlg in scene.get("dialogue", []):
                    paragraphs.extend(_fdx_dialogue_paragraphs(dlg))

                dual = scene.get("dual_dialogue")
                if dual is not None:
                    left_entry, right_entry = dual
                    left_xml = "\n  ".join(_fdx_dialogue_paragraphs(left_entry))
                    right_xml = "\n  ".join(_fdx_dialogue_paragraphs(right_entry))
                    paragraphs.append(
                        "    <Paragraph>\n      <DualDialogue>\n"
                        f"  {left_xml}\n  {right_xml}\n"
                        "      </DualDialogue>\n    </Paragraph>"
                    )

                transition = scene.get("transition")
                if transition:
                    trans_xml = escape(str(transition))
                    paragraphs.append(
                        f'    <Paragraph Type="Transition"><Text>{trans_xml}</Text></Paragraph>'
                    )

        content_body = "\n".join(paragraphs)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            f'<FinalDraft DocumentType="Script" Template="No" Version="{escape(version)}">\n'
            f"  <Content>\n{content_body}\n  </Content>\n"
            "</FinalDraft>\n"
        )

    return _make


@pytest.fixture
def make_fake_provider(
    sample_metadata: Callable[..., ScriptMetadata],
) -> Callable[..., BaseProvider]:
    class _FakeProvider(BaseProvider):
        def __init__(
            self,
            *,
            name: str,
            fmt: Literal["screenplay", "transcript"],
            allowed_hosts: set[str] | None,
            http: HttpClient,
            cache: CacheBackend | str | None,
            search_results: dict[str, list[SearchResult]] | list[SearchResult] | None,
            raw_scripts: (
                dict[str, RawScript] | RawScript | Callable[[SearchResult], RawScript] | None
            ),
            search_exceptions: dict[str, Exception] | Exception | None,
            fetch_exceptions: dict[str, Exception] | Exception | None,
            fetch_delay: float,
            use_cache: bool,
        ) -> None:
            super().__init__(http=http, cache=cache)
            self.name = name
            self.format = fmt
            if allowed_hosts is not None:
                self.allowed_hosts = allowed_hosts
            self._search_results = search_results
            self._raw_scripts = raw_scripts
            self._search_exceptions = search_exceptions
            self._fetch_exceptions = fetch_exceptions
            self.fetch_delay = fetch_delay
            self.use_cache = use_cache
            self.search_calls: list[str] = []
            self.fetch_calls: list[SearchResult] = []
            self.active_fetches: int = 0
            self.max_concurrent_fetches: int = 0

        async def search(self, query: str) -> list[SearchResult]:
            self.search_calls.append(query)
            if isinstance(self._search_exceptions, Exception):
                raise self._search_exceptions
            if isinstance(self._search_exceptions, dict):
                exc = self._search_exceptions.get(query) or self._search_exceptions.get(
                    query.strip().lower()
                )
                if exc is not None:
                    raise exc

            if self.use_cache:
                cached = await self._get_cached_search(query)
                if cached is not None:
                    return cached

            if isinstance(self._search_results, list):
                results = list(self._search_results)
            elif isinstance(self._search_results, dict):
                results = list(
                    self._search_results.get(query)
                    or self._search_results.get(query.strip().lower(), [])
                )
            else:
                slug = query.strip().lower().replace(" ", "-") or "script"
                results = [
                    SearchResult(
                        title=query.strip() or "Untitled",
                        url=f"https://www.{self.name}.example/scripts/{slug}.html",
                        source=self.name,
                        format=self.format,
                        score=95.0,
                    )
                ]

            if self.use_cache and results:
                await self._set_cached_search(query, results)
            return results

        async def fetch_raw(self, result: SearchResult) -> RawScript:
            self.fetch_calls.append(result)
            self.active_fetches += 1
            self.max_concurrent_fetches = max(self.max_concurrent_fetches, self.active_fetches)
            try:
                if self.fetch_delay > 0:
                    await asyncio.sleep(self.fetch_delay)

                if isinstance(self._fetch_exceptions, Exception):
                    raise self._fetch_exceptions
                if isinstance(self._fetch_exceptions, dict):
                    exc = (
                        self._fetch_exceptions.get(result.url)
                        or self._fetch_exceptions.get(result.title)
                        or self._fetch_exceptions.get(result.title.strip().lower())
                    )
                    if exc is not None:
                        raise exc

                if self.use_cache:
                    cached = await self._get_cached_raw(result.url)
                    if cached is not None:
                        return cached

                if callable(self._raw_scripts):
                    raw = self._raw_scripts(result)
                elif isinstance(self._raw_scripts, RawScript):
                    raw = self._raw_scripts
                elif isinstance(self._raw_scripts, dict):
                    raw = (
                        self._raw_scripts.get(result.url)
                        or self._raw_scripts.get(result.title)
                        or self._raw_scripts.get(result.title.strip().lower())
                    )
                    if raw is None:
                        raise LookupError(f"No RawScript configured for {result.url}")
                else:
                    raw = RawScript(
                        content="<pre>INT. ROOM - DAY\n\nNEO\nHello.\n</pre>",
                        content_type="html",
                        metadata=sample_metadata(
                            title=result.title,
                            source=result.source,
                            fmt=result.format,
                            url=result.url,
                        ),
                    )

                if self.use_cache:
                    await self._set_cached_raw(result.url, raw)
                return raw
            finally:
                self.active_fetches -= 1

    def _make(
        *,
        name: str = "scriptslug",
        fmt: Literal["screenplay", "transcript"] = "screenplay",
        allowed_hosts: set[str] | None = None,
        http: HttpClient | None = None,
        cache: CacheBackend | str | None = None,
        search_results: dict[str, list[SearchResult]] | list[SearchResult] | None = None,
        raw_scripts: (
            dict[str, RawScript] | RawScript | Callable[[SearchResult], RawScript] | None
        ) = None,
        search_exceptions: dict[str, Exception] | Exception | None = None,
        fetch_exceptions: dict[str, Exception] | Exception | None = None,
        fetch_delay: float = 0.0,
        use_cache: bool = False,
    ) -> _FakeProvider:
        return _FakeProvider(
            name=name,
            fmt=fmt,
            allowed_hosts=allowed_hosts,
            http=http or HttpClient(min_interval=0.0),
            cache=cache,
            search_results=search_results,
            raw_scripts=raw_scripts,
            search_exceptions=search_exceptions,
            fetch_exceptions=fetch_exceptions,
            fetch_delay=fetch_delay,
            use_cache=use_cache,
        )

    return _make


class _FakeRedisClient:
    def __init__(self, *, scan_page_size: int | None = None, fail_info: bool = False) -> None:
        self.store: dict[str, tuple[bytes | str, int | None]] = {}
        self._expirations: dict[str, float | None] = {}
        self.scan_page_size = scan_page_size
        self.fail_info = fail_info
        self.closed = False
        self.flushdb_called = False
        self.scan_calls = 0
        self._scan_snapshot: list[str] = []

    def _is_expired(self, key: str) -> bool:
        expires_at = self._expirations.get(key)
        if expires_at is not None and time.monotonic() >= expires_at:
            self.store.pop(key, None)
            self._expirations.pop(key, None)
            return True
        return False

    def _live_keys(self, match: str | None = None) -> list[str]:
        keys: list[str] = []
        for key in list(self.store):
            if self._is_expired(key):
                continue
            if match is None or fnmatch.fnmatchcase(key, match):
                keys.append(key)
        return sorted(keys)

    async def get(self, key: str) -> bytes | str | None:
        if self._is_expired(key):
            return None
        entry = self.store.get(key)
        return entry[0] if entry is not None else None

    async def set(self, key: str, value: bytes | str, ex: int | None = None) -> None:
        self.store[key] = (value, ex)
        self._expirations[key] = (time.monotonic() + ex) if ex is not None else None

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            self._expirations.pop(key, None)
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    async def scan(
        self,
        cursor: int | bytes | str = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        self.scan_calls += 1
        idx = int(cursor) if isinstance(cursor, (int, bytes, str)) else 0
        if idx == 0:
            self._scan_snapshot = self._live_keys(match)
        step = (
            self.scan_page_size
            if self.scan_page_size is not None and self.scan_page_size > 0
            else (count if count is not None and count > 0 else len(self._scan_snapshot) or 1)
        )
        batch = [k for k in self._scan_snapshot[idx : idx + step] if k in self.store]
        next_cursor = idx + step if idx + step < len(self._scan_snapshot) else 0
        return next_cursor, batch

    async def scan_iter(
        self,
        match: str | None = None,
        count: int | None = None,
    ) -> AsyncIterator[str]:
        cursor: int = 0
        while True:
            cursor, batch = await self.scan(cursor=cursor, match=match, count=count)
            for key in batch:
                yield key
            if cursor == 0:
                break

    async def info(self, section: str | None = None) -> dict[str, Any]:
        if self.fail_info:
            raise RuntimeError("NOPERM INFO command disabled")
        live = self._live_keys()
        used_memory = sum(
            len(self.store[k][0].encode("utf-8"))
            if isinstance(self.store[k][0], str)
            else len(self.store[k][0])
            for k in live
        )
        return {"used_memory": used_memory, "db0": {"keys": len(live)}}

    async def dbsize(self) -> int:
        return len(self._live_keys())

    async def flushdb(self, asynchronous: bool = False) -> bool:
        self.flushdb_called = True
        self.store.clear()
        self._expirations.clear()
        return True

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_redis_client_factory() -> Callable[..., _FakeRedisClient]:
    def _factory(*, scan_page_size: int | None = None, fail_info: bool = False) -> _FakeRedisClient:
        return _FakeRedisClient(scan_page_size=scan_page_size, fail_info=fail_info)

    return _factory


@pytest.fixture
def make_mock_http_client() -> Callable[..., HttpClient]:
    def _make(
        responses: list[httpx.Response | Exception] | httpx.Response | Exception | None = None,
        *,
        max_retries: int = 1,
        min_interval: float = 0.0,
        backoff_base: float = 0.0,
        max_redirects: int = 5,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        **http_kwargs: Any,
    ) -> HttpClient:
        client = HttpClient(
            max_retries=max_retries,
            min_interval=min_interval,
            backoff_base=backoff_base,
            max_redirects=max_redirects,
            max_response_bytes=max_response_bytes,
            **http_kwargs,
        )
        mock_inner = AsyncMock()
        mock_inner.is_closed = False
        mock_inner.aclose = AsyncMock()

        if responses is None:
            mock_inner.request.return_value = httpx.Response(
                status_code=200,
                content=b"ok",
                request=httpx.Request("GET", "https://example.com/ok"),
            )
        elif isinstance(responses, list):
            mock_inner.request.side_effect = list(responses)
        elif isinstance(responses, Exception):
            mock_inner.request.side_effect = responses
        else:
            mock_inner.request.return_value = responses

        client._client = mock_inner
        return client

    return _make


@pytest.fixture
def patch_cli_aggregator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., Path]:
    def _patch(
        providers: dict[str, BaseProvider] | BaseProvider,
        *,
        cache_subdir: str = "rtfs_cache",
    ) -> Path:
        providers_dict = (
            {providers.name: providers}
            if isinstance(providers, BaseProvider)
            else dict(providers)
        )
        if not providers_dict:
            raise ValueError("patch_cli_aggregator requires at least one provider")

        cache_dir = tmp_path / cache_subdir
        real_cls = ScriptAggregator

        def _factory(
            http: HttpClient | None = None,
            cache: CacheBackend | str | None = None,
            providers: dict[str, BaseProvider] | None = None,
        ) -> ScriptAggregator:
            effective_cache: CacheBackend | str | None = cache
            if effective_cache is None and "RTFS_CACHE_URL" not in os.environ:
                effective_cache = f"disk://{cache_dir}"
            agg = real_cls(
                http=http,
                cache=effective_cache,
                providers=providers or providers_dict,
            )
            for prov in agg.providers.values():
                prov.cache = agg.cache
            return agg

        import rtfs.cli.main as cli_main
        import rtfs.core.aggregator as agg_mod

        monkeypatch.setattr(cli_main, "ScriptAggregator", _factory)
        monkeypatch.setattr(agg_mod, "ScriptAggregator", _factory)
        return cache_dir

    return _patch


@dataclass
class OfflineNetworkRecorder:
    connect_calls: list[tuple[str, int]] = field(default_factory=list)
    tls_hostnames: list[str | None] = field(default_factory=list)
    sent_payloads: list[bytes] = field(default_factory=list)


class _OfflineByteStream(anyio.abc.ByteStream):
    def __init__(self, chunks: list[bytes], sent_payloads: list[bytes]) -> None:
        self._chunks = list(chunks)
        self._sent_payloads = sent_payloads
        self.closed = False

    async def receive(self, max_bytes: int = 65536) -> bytes:
        if self.closed or not self._chunks:
            raise anyio.EndOfStream
        chunk = self._chunks.pop(0)
        if len(chunk) > max_bytes:
            self._chunks.insert(0, chunk[max_bytes:])
            return chunk[:max_bytes]
        return chunk

    async def send(self, item: bytes) -> None:
        self._sent_payloads.append(bytes(item))

    async def send_eof(self) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True

    @property
    def extra_attributes(self) -> Mapping[Any, Callable[[], Any]]:
        return {}


@pytest.fixture
def make_addrinfo_resolver() -> Callable[..., Callable[..., Any]]:
    def _build(
        mapping_or_fn: (
            dict[str, Sequence[str]] | Sequence[str] | Callable[[str, int], Sequence[str]]
        ),
    ) -> Callable[..., Any]:
        async def _resolver(
            host: str,
            port: int | None = None,
            **_kwargs: Any,
        ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            resolved_port = int(port or 443)
            if callable(mapping_or_fn):
                ips = mapping_or_fn(host, resolved_port)
            elif isinstance(mapping_or_fn, dict):
                ips = mapping_or_fn.get(host, [])
            else:
                ips = mapping_or_fn

            entries: list[tuple[int, int, int, str, tuple[str, int]]] = []
            for ip in ips:
                family = socket.AF_INET6 if ":" in ip else socket.AF_INET
                entries.append(
                    (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, resolved_port))
                )
            return entries

        return _resolver

    return _build


@pytest.fixture
def patch_offline_network(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., OfflineNetworkRecorder]:
    def _patch(
        responses: list[bytes | list[bytes]]
        | Callable[[str, int], bytes | list[bytes]]
        | None = None,
    ) -> OfflineNetworkRecorder:
        recorder = OfflineNetworkRecorder()
        queued = list(responses) if isinstance(responses, list) else None

        async def _fake_connect_tcp(
            remote_host: str,
            remote_port: int,
            **_kwargs: Any,
        ) -> _OfflineByteStream:
            recorder.connect_calls.append((str(remote_host), int(remote_port)))
            if callable(responses):
                raw = responses(str(remote_host), int(remote_port))
                chunks = [raw] if isinstance(raw, bytes) else list(raw)
            elif queued is not None and queued:
                raw = queued.pop(0)
                chunks = [raw] if isinstance(raw, bytes) else list(raw)
            else:
                chunks = [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"]
            return _OfflineByteStream(chunks, recorder.sent_payloads)

        async def _fake_tls_wrap(
            transport_stream: anyio.abc.ByteStream,
            *,
            hostname: str | None = None,
            **_kwargs: Any,
        ) -> anyio.abc.ByteStream:
            recorder.tls_hostnames.append(hostname)
            return transport_stream

        monkeypatch.setattr(anyio, "connect_tcp", _fake_connect_tcp)
        monkeypatch.setattr(anyio.streams.tls.TLSStream, "wrap", _fake_tls_wrap)
        return recorder

    return _patch
