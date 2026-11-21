from __future__ import annotations

import ipaddress
import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from rtfs.core.cache import create_cache
from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    Transition,
)
from rtfs.exporters.fountain_exp import export_fountain, export_txt
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.stats_exp import compute_stats
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser

# ---------------------------------------------------------------------------
# F1: Dual-column simultaneous dialogue (Tier 1)
# ---------------------------------------------------------------------------


def test_f1_pdf_parser_detects_dual_column_dialogue_and_preserves_order(
    make_dual_column_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    pdf_bytes = make_dual_column_pdf_bytes()
    raw = RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())

    doc = PdfScreenplayParser().parse(raw)

    assert len(doc.scenes) == 1
    elements = doc.scenes[0].elements
    assert len(elements) == 5
    assert isinstance(elements[0], Action)
    assert "Monitors flicker" in elements[0].text

    reg = elements[1]
    assert isinstance(reg, Dialogue)
    assert reg.character == "MORPHEUS"
    assert reg.lines == "Wait for my signal."
    assert reg.dual is False

    left = elements[2]
    assert isinstance(left, Dialogue)
    assert left.character == "TRINITY"
    assert left.lines == "Watch the door!"
    assert left.dual is False

    right = elements[3]
    assert isinstance(right, Dialogue)
    assert right.character == "NEO"
    assert right.lines == "I have the key!"
    assert right.dual is True

    assert isinstance(elements[4], Action)
    assert "Both move at once." in elements[4].text


def test_f1_pdf_parser_preserves_modifiers_and_parentheticals_in_dual_columns(
    make_dual_column_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    pdf_bytes = make_dual_column_pdf_bytes(
        regular_dialogue=None,
        left_character="ALICE (V.O.)",
        left_parenthetical="(whispering)",
        left_lines=["Stay low."],
        right_character="BOB (O.S.)",
        right_parenthetical="(shouting)",
        right_lines=["Get down now!"],
        trailing_action=None,
    )
    raw = RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())

    doc = PdfScreenplayParser().parse(raw)
    dialogues = [el for el in doc.scenes[0].elements if isinstance(el, Dialogue)]
    assert len(dialogues) == 2

    left, right = dialogues
    assert left.character == "ALICE"
    assert left.modifiers == ["V.O."]
    assert left.parenthetical == "whispering"
    assert left.lines == "Stay low."
    assert left.dual is False

    assert right.character == "BOB"
    assert right.modifiers == ["O.S."]
    assert right.parenthetical == "shouting"
    assert right.lines == "Get down now!"
    assert right.dual is True


def test_f1_fountain_and_txt_export_emit_dual_caret_with_modifiers(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    doc = ScriptDocument(
        metadata=sample_metadata(),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. CONTROL ROOM - NIGHT",
                location="CONTROL ROOM",
                time_of_day="NIGHT",
                elements=[
                    Dialogue(character="ALICE", lines="Opening the gate.", dual=False),
                    Dialogue(
                        character="BOB",
                        modifiers=["O.S."],
                        parenthetical="tense",
                        lines="Hurry up!",
                        dual=True,
                    ),
                    Dialogue(character="CAROL", lines="Wait for me!", dual=True),
                ],
            )
        ],
    )

    fountain = export_fountain(doc)
    txt = export_txt(doc)

    assert txt == fountain
    assert "\nALICE\nOpening the gate.\n" in fountain
    assert "\nBOB (O.S.)^\n(tense)\nHurry up!\n" in fountain
    assert "\nCAROL^\nWait for me!\n" in fountain


def test_f1_compute_stats_counts_dual_dialogue_turns_and_words(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    doc = ScriptDocument(
        metadata=sample_metadata(),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. LAB - DAY",
                location="LAB",
                time_of_day="DAY",
                elements=[
                    Action(text="Sparks fly everywhere."),  # 3 words
                    Dialogue(character="ALICE", lines="One two three", dual=False),  # 3 words
                    Dialogue(character="BOB", lines="Four five", dual=True),  # 2 words
                    Dialogue(character="BOB", lines="Six", dual=False),  # 1 word
                ],
            )
        ],
    )

    stats = compute_stats(doc)
    assert stats.action_words == 3
    assert stats.dialogue_words == 6
    assert stats.dialogue_to_action_ratio == 2.0
    by_char = {c.character: c for c in stats.top_characters}
    assert by_char["BOB"].dialogue_turns == 2
    assert by_char["BOB"].word_count == 3
    assert by_char["ALICE"].dialogue_turns == 1
    assert by_char["ALICE"].word_count == 3


def test_f1_dialogue_dual_default_false_and_json_roundtrip(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    default_dlg = Dialogue(character="NEO", lines="Whoa.")
    assert default_dlg.dual is False

    doc = ScriptDocument(
        metadata=sample_metadata(),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. DOJO - DAY",
                elements=[
                    default_dlg,
                    Dialogue(character="MORPHEUS", lines="Show me.", dual=True),
                ],
            )
        ],
    )

    raw_json = export_json(doc)
    payload = json.loads(raw_json)
    assert payload["scenes"][0]["elements"][0]["dual"] is False
    assert payload["scenes"][0]["elements"][1]["dual"] is True

    restored = ScriptDocument.model_validate_json(raw_json)
    assert restored == doc


# ---------------------------------------------------------------------------
# F2: Final Draft (.fdx) XML parser & exporter (Tier 1)
# ---------------------------------------------------------------------------


def test_f2_fdx_parser_parses_scenes_elements_and_multi_text_runs(
    make_fdx_xml: Callable[..., str],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.parsers.fdx import FdxParser

    xml_text = make_fdx_xml(include_dual=False)
    raw = RawScript(content=xml_text, content_type="fdx", metadata=sample_metadata())

    doc = FdxParser().parse(raw)

    assert len(doc.scenes) == 2
    s1 = doc.scenes[0]
    assert s1.scene_number == 1
    assert s1.heading == "INT. BUNKER - NIGHT"
    assert s1.location == "BUNKER"
    assert s1.time_of_day == "NIGHT"
    assert isinstance(s1.elements[0], Action)
    assert s1.elements[0].text == "Rain streaks down the glass."

    dlg = s1.elements[1]
    assert isinstance(dlg, Dialogue)
    assert dlg.character == "MORPHEUS"
    assert dlg.modifiers == ["V.O."]
    assert dlg.parenthetical == "calmly"
    assert dlg.lines == "Free your mind."
    assert dlg.dual is False

    assert isinstance(s1.elements[2], Transition)
    assert s1.elements[2].text == "CUT TO:"

    s2 = doc.scenes[1]
    assert s2.scene_number == 2
    assert s2.heading == "EXT. ROOFTOP - DAWN"
    assert s2.location == "ROOFTOP"
    assert s2.time_of_day == "DAWN"


def test_f2_fdx_parser_pairs_dual_dialogue_blocks(
    make_fdx_xml: Callable[..., str],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.parsers.fdx import FdxParser

    xml_text = make_fdx_xml(include_dual=True)
    raw = RawScript(content=xml_text, content_type="fdx", metadata=sample_metadata())

    doc = FdxParser().parse(raw)
    dialogues = [el for el in doc.scenes[0].elements if isinstance(el, Dialogue)]
    assert len(dialogues) == 3

    assert dialogues[0].character == "MORPHEUS"
    assert dialogues[0].dual is False

    assert dialogues[1].character == "TRINITY"
    assert dialogues[1].parenthetical == "urgent"
    assert dialogues[1].lines == "Watch the door!"
    assert dialogues[1].dual is False

    assert dialogues[2].character == "NEO"
    assert dialogues[2].parenthetical == "focused"
    assert dialogues[2].lines == "I see them."
    assert dialogues[2].dual is True


def test_f2_export_fdx_generates_valid_final_draft_xml_with_dual_dialogue(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.exporters.fdx_exp import export_fdx

    doc = ScriptDocument(
        metadata=sample_metadata(title="Dual Test", writers=["Alice", "Bob"]),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. HALLWAY - NIGHT",
                elements=[
                    Action(text="Lights flicker."),
                    Dialogue(character="ALICE", lines="Left side.", dual=False),
                    Dialogue(character="BOB", lines="Right side.", dual=True),
                    Transition(text="CUT TO:"),
                ],
            )
        ],
    )

    xml_out = export_fdx(doc)
    root = ET.fromstring(xml_out)

    assert root.tag == "FinalDraft"
    assert root.attrib["DocumentType"] == "Script"
    assert root.attrib["Template"] == "No"
    assert root.attrib["Version"] == "5"

    content = root.find("Content")
    assert content is not None
    para_types = [p.attrib.get("Type") for p in content.findall("Paragraph")]
    assert "Scene Heading" in para_types
    assert "Action" in para_types
    assert "Transition" in para_types

    dual_nodes = content.findall(".//DualDialogue")
    assert len(dual_nodes) == 1
    dual_chars = [
        "".join(p.itertext()).strip()
        for p in dual_nodes[0].findall("Paragraph")
        if p.attrib.get("Type") == "Character"
    ]
    assert dual_chars == ["ALICE", "BOB"]


def test_f2_script_document_export_fdx_reparse_roundtrip(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.exporters.fdx_exp import export_fdx
    from rtfs.parsers.fdx import FdxParser

    meta = sample_metadata(title="Roundtrip Script", writers=["Wachowski"])
    doc = ScriptDocument(
        metadata=meta,
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. COMMAND DECK - NIGHT",
                location="COMMAND DECK",
                time_of_day="NIGHT",
                elements=[
                    Action(text="Alarms blare."),
                    Dialogue(
                        character="TANK",
                        modifiers=["O.S."],
                        parenthetical="shouting",
                        lines="Operator standing by.",
                        dual=False,
                    ),
                    Dialogue(character="TRINITY", lines="Cover me!", dual=False),
                    Dialogue(
                        character="NEO",
                        parenthetical="nodding",
                        lines="On your six.",
                        dual=True,
                    ),
                    Transition(text="FADE OUT."),
                ],
            ),
            Scene(
                scene_number=2,
                heading="EXT. CITY - DAY",
                location="CITY",
                time_of_day="DAY",
                elements=[Action(text="Crowds move below.")],
            ),
        ],
    )

    xml_out = export_fdx(doc)
    reparsed = FdxParser().parse(RawScript(content=xml_out, content_type="fdx", metadata=meta))

    assert reparsed.metadata == doc.metadata
    assert reparsed.scenes == doc.scenes


def test_f2_raw_script_accepts_str_and_utf8_bytes_with_fdx_content_type(
    make_fdx_xml: Callable[..., str],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.parsers.fdx import FdxParser

    xml_str = make_fdx_xml(include_dual=True)
    meta = sample_metadata()

    raw_str = RawScript(content=xml_str, content_type="fdx", metadata=meta)
    raw_bytes = RawScript(content=xml_str.encode("utf-8"), content_type="fdx", metadata=meta)

    parser = FdxParser()
    assert parser.parse(raw_str) == parser.parse(raw_bytes)


# ---------------------------------------------------------------------------
# F3: DNS resolution pinning in HttpClient (Tier 1)
# ---------------------------------------------------------------------------


def test_f3_is_public_ip_and_validate_public_http_url_accept_public_targets() -> None:
    from rtfs.core.http import is_public_ip, validate_public_http_url

    assert is_public_ip(ipaddress.ip_address("93.184.216.34")) is True
    assert is_public_ip(ipaddress.ip_address("2606:4700:4700::1111")) is True

    assert (
        validate_public_http_url("https://imsdb.com/scripts/Matrix.html")
        == "https://imsdb.com/scripts/Matrix.html"
    )
    assert (
        validate_public_http_url("http://93.184.216.34/script.html")
        == "http://93.184.216.34/script.html"
    )


async def test_f3_http_client_pins_resolved_public_ip_and_preserves_host_and_sni(
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network(
        [b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\nConnection: close\r\n\r\nscript"]
    )
    resolver_calls: list[tuple[str, int]] = []

    def _lookup(host: str, port: int) -> list[str]:
        resolver_calls.append((host, port))
        return ["93.184.216.34"]

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=make_addrinfo_resolver(_lookup),
    ) as client:
        text = await client.get_text("https://imsdb.com/scripts/Matrix.html")

    assert text == "script"
    assert resolver_calls == [("imsdb.com", 443)]
    assert net.connect_calls == [("93.184.216.34", 443)]
    assert net.tls_hostnames == ["imsdb.com"]
    assert b"Host: imsdb.com\r\n" in b"".join(net.sent_payloads)


async def test_f3_http_client_blocks_private_dns_resolution_without_retries(
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network()
    resolver_calls = 0

    def _lookup(_host: str, _port: int) -> list[str]:
        nonlocal resolver_calls
        resolver_calls += 1
        return ["127.0.0.1"]

    async with HttpClient(
        max_retries=3,
        min_interval=0.0,
        backoff_base=0.0,
        resolver=make_addrinfo_resolver(_lookup),
    ) as client:
        with pytest.raises(ValueError, match="Blocked non-public IP"):
            await client.get_text("https://rebind.example/secret")

    assert resolver_calls == 1
    assert net.connect_calls == []


async def test_f3_http_client_blocks_toctou_dns_rebinding_on_subsequent_connection(
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network(
        [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"]
    )
    answers = [["93.184.216.34"], ["10.0.0.1"]]
    calls = 0

    def _lookup(_host: str, _port: int) -> list[str]:
        nonlocal calls
        idx = min(calls, len(answers) - 1)
        calls += 1
        return answers[idx]

    async with HttpClient(
        max_retries=3,
        min_interval=0.0,
        backoff_base=0.0,
        resolver=make_addrinfo_resolver(_lookup),
    ) as client:
        assert await client.get_text("http://rebind.example/first") == "ok"
        with pytest.raises(ValueError, match="Blocked non-public IP"):
            await client.get_text("http://rebind.example/second")

    assert calls == 2
    assert net.connect_calls == [("93.184.216.34", 80)]


async def test_f3_http_client_disables_trust_env_proxies(
    monkeypatch: pytest.MonkeyPatch,
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9999")

    net = patch_offline_network()
    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=make_addrinfo_resolver({"imsdb.com": ["93.184.216.34"]}),
    ) as client:
        inner = await client._get_client()
        assert inner.trust_env is False
        assert await client.get_text("https://imsdb.com/scripts/Matrix.html") == "ok"

    assert net.connect_calls == [("93.184.216.34", 443)]


async def test_f3_http_client_preserves_asyncmock_client_seam(
    make_mock_http_client: Callable[..., Any],
) -> None:
    retry_client = make_mock_http_client(
        [
            httpx.Response(
                503,
                content=b"busy",
                request=httpx.Request("GET", "https://imsdb.com/a"),
            ),
            httpx.Response(
                200,
                content=b"ready",
                request=httpx.Request("GET", "https://imsdb.com/a"),
            ),
        ],
        max_retries=2,
    )
    assert await retry_client.get_text("https://imsdb.com/a") == "ready"

    redirect_client = make_mock_http_client(
        [
            httpx.Response(
                302,
                headers={"location": "/scripts/Matrix.html"},
                request=httpx.Request("POST", "https://imsdb.com/search.php"),
            ),
            httpx.Response(
                200,
                content=b"found",
                request=httpx.Request("GET", "https://imsdb.com/scripts/Matrix.html"),
            ),
        ]
    )
    resp = await redirect_client.request(
        "POST",
        "https://imsdb.com/search.php",
        data={"q": "Matrix"},
    )
    assert resp.text == "found"

    ssrf_client = make_mock_http_client(
        [
            httpx.Response(
                302,
                headers={"location": "http://127.0.0.1/admin"},
                request=httpx.Request("GET", "https://imsdb.com/a"),
            )
        ]
    )
    with pytest.raises(ValueError, match="Blocked non-public IP"):
        await ssrf_client.get_text("https://imsdb.com/a")


# ---------------------------------------------------------------------------
# F4: Cache backend info() & clear() (Tier 1)
# ---------------------------------------------------------------------------


async def test_f4_all_backends_satisfy_cache_protocol_and_return_cache_info(
    tmp_path: Path,
    fake_redis_client_factory: Callable[..., Any],
) -> None:
    from rtfs.core.cache import (
        CacheBackend,
        CacheInfo,
        DiskCacheBackend,
        MemoryCacheBackend,
        NullCacheBackend,
        RedisCacheBackend,
    )

    backends = [
        MemoryCacheBackend(),
        DiskCacheBackend(tmp_path / "disk"),
        NullCacheBackend(),
        RedisCacheBackend(client=fake_redis_client_factory()),
    ]
    try:
        for backend in backends:
            assert isinstance(backend, CacheBackend)
            info = await backend.info()
            assert isinstance(info, CacheInfo)
    finally:
        for backend in backends:
            await backend.close()


async def test_f4_memory_cache_info_and_clear() -> None:
    from rtfs.core.cache import CacheInfo, MemoryCacheBackend

    cache = MemoryCacheBackend()
    assert await cache.info() == CacheInfo(
        backend="memory",
        location=None,
        entries=0,
        size_bytes=0,
    )

    await cache.set("k1", b"hello")
    await cache.set("k2", b"world!")
    populated = await cache.info()
    assert populated.backend == "memory"
    assert populated.entries == 2
    assert populated.size_bytes == 11

    await cache.clear()
    assert await cache.get("k1") is None
    assert await cache.get("k2") is None
    cleared = await cache.info()
    assert cleared.entries == 0
    assert cleared.size_bytes == 0


async def test_f4_disk_cache_info_and_clear(tmp_path: Path) -> None:
    from rtfs.core.cache import DiskCacheBackend

    cache_dir = tmp_path / "disk_cache"
    cache = DiskCacheBackend(cache_dir)
    try:
        empty = await cache.info()
        assert empty.backend == "disk"
        assert empty.location == str(cache_dir)
        assert empty.entries == 0

        await cache.set("k1", b"script-one")
        await cache.set("k2", b"script-two")
        populated = await cache.info()
        assert populated.backend == "disk"
        assert populated.location == str(cache_dir)
        assert populated.entries == 2
        assert populated.size_bytes is not None and populated.size_bytes > 0

        await cache.clear()
        assert await cache.get("k1") is None
        cleared = await cache.info()
        assert cleared.entries == 0
        assert cleared.size_bytes is not None and cleared.size_bytes >= 0
    finally:
        await cache.close()


async def test_f4_null_cache_info_and_clear() -> None:
    from rtfs.core.cache import NullCacheBackend

    cache = NullCacheBackend()
    await cache.set("k1", b"ignored")
    await cache.clear()
    info = await cache.info()
    assert info.backend == "null"
    assert info.location is None
    assert info.entries in (0, None)
    assert info.size_bytes in (0, None)


async def test_f4_redis_cache_info_and_clear_via_fake_client(
    fake_redis_client_factory: Callable[..., Any],
) -> None:
    from rtfs.core.cache import RedisCacheBackend

    fake_client = fake_redis_client_factory()
    cache = RedisCacheBackend(
        url="redis://localhost:6379/0",
        prefix="e2e:",
        client=fake_client,
    )
    try:
        await cache.set("a", b"payload-a")
        await cache.set("b", b"payload-b")
        info = await cache.info()
        assert info.backend == "redis"
        assert info.location == "redis://localhost:6379/0"
        assert info.entries == 2
        assert info.size_bytes is not None and info.size_bytes > 0

        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None
        assert (await cache.info()).entries == 0
    finally:
        await cache.close()


async def test_f4_create_cache_factory_integration_info_and_clear(tmp_path: Path) -> None:
    disk_dir = tmp_path / "factory_disk"
    for uri, expected_backend in (
        ("memory://", "memory"),
        (f"disk://{disk_dir}", "disk"),
        ("none://", "null"),
    ):
        backend = create_cache(uri)
        try:
            await backend.set("item", b"data")
            info = await backend.info()
            assert info.backend == expected_backend
            await backend.clear()
            assert (await backend.info()).entries in (0, None)
        finally:
            await backend.close()
