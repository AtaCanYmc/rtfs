from __future__ import annotations

import asyncio
import ipaddress
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.parsers import expat

import httpx
import pytest
from pydantic import ValidationError

from rtfs.core.cache import create_cache
from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    ScriptMetadata,
)
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser

# ---------------------------------------------------------------------------
# F1: Dual-column simultaneous dialogue boundaries (Tier 2)
# ---------------------------------------------------------------------------


def test_f1_non_overlapping_y_columns_stay_single_dialogue(
    make_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    pdf_bytes = make_pdf_bytes(
        [
            [
                (72.0, 85.0, "INT. STUDIO - DAY"),
                (216.0, 140.0, "ALICE"),
                (144.0, 154.0, "Left column earlier."),
                (280.0, 260.0, "BOB"),
                (240.0, 274.0, "Right column much later."),
            ]
        ]
    )
    doc = PdfScreenplayParser().parse(
        RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())
    )
    dialogues = [el for el in doc.scenes[0].elements if isinstance(el, Dialogue)]
    assert len(dialogues) == 2
    assert all(dlg.dual is False for dlg in dialogues)


def test_f1_small_x_separation_on_same_column_not_dual(
    make_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    pdf_bytes = make_pdf_bytes(
        [
            [
                (72.0, 85.0, "INT. OFFICE - DAY"),
                (180.0, 130.0, "ALICE"),
                (120.0, 144.0, "Hello there."),
                (192.0, 190.0, "BOB"),
                (132.0, 204.0, "Good morning."),
                (216.0, 255.0, "CAROL"),
                (144.0, 270.0, "Wait"),
                (168.0, 270.0, "now."),
            ]
        ]
    )
    doc = PdfScreenplayParser().parse(
        RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())
    )
    dialogues = [el for el in doc.scenes[0].elements if isinstance(el, Dialogue)]
    assert len(dialogues) >= 3
    assert all(dlg.dual is False for dlg in dialogues)


def test_f1_staggered_partial_y_overlap_asymmetric_lines_and_trailing_action(
    make_dual_column_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    pdf_bytes = make_dual_column_pdf_bytes(
        regular_dialogue=None,
        left_character="ALICE",
        left_parenthetical="(fast)",
        left_lines=["Line one.", "Line two.", "Line three.", "Line four."],
        right_character="BOB",
        right_lines=["Short reply."],
        y_dual=200.0,
        y_right_offset=28.0,
        trailing_action="Silence falls over the bunker.",
    )
    doc = PdfScreenplayParser().parse(
        RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())
    )
    elements = doc.scenes[0].elements
    dialogues = [el for el in elements if isinstance(el, Dialogue)]
    assert len(dialogues) == 2

    left, right = dialogues
    assert left.character == "ALICE"
    assert left.parenthetical == "fast"
    assert left.lines == "Line one. Line two. Line three. Line four."
    assert left.dual is False

    assert right.character == "BOB"
    assert right.lines == "Short reply."
    assert right.dual is True

    assert isinstance(elements[-1], Action)
    assert "Silence falls over the bunker." in elements[-1].text


def test_f1_cross_page_same_y_not_paired_and_multiple_dual_blocks_same_page(
    make_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    pdf_bytes = make_pdf_bytes(
        [
            [
                (72.0, 85.0, "INT. BRIDGE - NIGHT"),
                (216.0, 140.0, "ALICE"),
                (144.0, 154.0, "First page regular line."),
                (144.0, 230.0, "TRINITY"),
                (108.0, 244.0, "Left one."),
                (378.0, 230.0, "NEO"),
                (342.0, 244.0, "Right one."),
                (72.0, 295.0, "A beat passes."),
                (144.0, 345.0, "MORPHEUS"),
                (108.0, 359.0, "Left two."),
                (378.0, 345.0, "TANK"),
                (342.0, 359.0, "Right two."),
            ],
            [
                (72.0, 85.0, "EXT. STREET - DAY"),
                (280.0, 140.0, "BOB"),
                (240.0, 154.0, "Second page regular line."),
            ],
        ]
    )
    doc = PdfScreenplayParser().parse(
        RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())
    )
    assert len(doc.scenes) == 2

    s1_dialogues = [el for el in doc.scenes[0].elements if isinstance(el, Dialogue)]
    assert [(d.character, d.dual) for d in s1_dialogues] == [
        ("ALICE", False),
        ("TRINITY", False),
        ("NEO", True),
        ("MORPHEUS", False),
        ("TANK", True),
    ]

    s2_dialogues = [el for el in doc.scenes[1].elements if isinstance(el, Dialogue)]
    assert [(d.character, d.dual) for d in s2_dialogues] == [("BOB", False)]


def test_f1_strict_bool_validation_and_header_footer_cutoff(
    make_pdf_bytes: Callable[..., bytes],
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    with pytest.raises(ValidationError):
        Dialogue(character="NEO", lines="Hi.", dual="true")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        Dialogue(character="NEO", lines="Hi.", dual=1)  # type: ignore[arg-type]

    pdf_bytes = make_pdf_bytes(
        [
            [
                (72.0, 35.0, "SECRET HEADER DRAFT"),
                (72.0, 100.0, "INT. VAULT - NIGHT"),
                (216.0, 150.0, "CYPHER"),
                (144.0, 164.0, "Inside the safe band."),
                (72.0, 760.0, "CONFIDENTIAL FOOTER"),
            ]
        ]
    )
    doc = PdfScreenplayParser().parse(
        RawScript(content=pdf_bytes, content_type="pdf", metadata=sample_metadata())
    )
    assert len(doc.scenes) == 1
    assert doc.scenes[0].heading == "INT. VAULT - NIGHT"
    joined_text = " ".join(
        el.lines if isinstance(el, Dialogue) else el.text for el in doc.scenes[0].elements
    )
    assert "SECRET HEADER" not in joined_text
    assert "CONFIDENTIAL FOOTER" not in joined_text
    assert "Inside the safe band." in joined_text


# ---------------------------------------------------------------------------
# F2: Final Draft (.fdx) XML parser & exporter boundaries (Tier 2)
# ---------------------------------------------------------------------------


def test_f2_fdx_blocks_xxe_doctype_entity_attack(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.parsers.fdx import FdxParser

    xxe_payload = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        '<FinalDraft DocumentType="Script" Template="No" Version="5">\n'
        "  <Content>\n"
        '    <Paragraph Type="Action"><Text>&xxe;</Text></Paragraph>\n'
        "  </Content>\n"
        "</FinalDraft>\n"
    )
    raw = RawScript(content=xxe_payload, content_type="fdx", metadata=sample_metadata())
    with pytest.raises((ValueError, expat.ExpatError, ET.ParseError)):
        FdxParser().parse(raw)


def test_f2_fdx_blocks_billion_laughs_xml_bomb(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.parsers.fdx import FdxParser

    bomb_payload = (
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE lolz [\n"
        '  <!ENTITY lol "lol">\n'
        '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
        '  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">\n'
        "]>\n"
        '<FinalDraft DocumentType="Script" Template="No" Version="5">\n'
        "  <Content>\n"
        '    <Paragraph Type="Action"><Text>&lol3;</Text></Paragraph>\n'
        "  </Content>\n"
        "</FinalDraft>\n"
    )
    raw = RawScript(content=bomb_payload, content_type="fdx", metadata=sample_metadata())
    with pytest.raises((ValueError, expat.ExpatError, ET.ParseError)):
        FdxParser().parse(raw)


def test_f2_export_fdx_strips_invalid_xml10_control_chars_preserves_whitespace(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.exporters.fdx_exp import export_fdx
    from rtfs.parsers.fdx import FdxParser

    dirty = "\x00\x01\x08\x0b\x0c\x1f"
    doc = ScriptDocument(
        metadata=sample_metadata(title=f"Clean{dirty}Title"),
        scenes=[
            Scene(
                scene_number=1,
                heading=f"INT. ROOM{dirty} - DAY",
                elements=[
                    Action(text=f"Line one.\n\tLine{dirty} two."),
                    Dialogue(character=f"NE{dirty}O", lines=f"Hello{dirty}\tworld."),
                ],
            )
        ],
    )

    xml_out = export_fdx(doc)
    for bad_ch in dirty:
        assert bad_ch not in xml_out

    ET.fromstring(xml_out)
    reparsed = FdxParser().parse(
        RawScript(content=xml_out, content_type="fdx", metadata=sample_metadata())
    )
    assert isinstance(reparsed.scenes[0].elements[0], Action)
    assert reparsed.scenes[0].elements[0].text == "Line one. Line two."
    assert isinstance(reparsed.scenes[0].elements[1], Dialogue)
    assert reparsed.scenes[0].elements[1].lines == "Hello world."


@pytest.mark.parametrize(
    "bad_content",
    [
        "",
        "   ",
        "<FinalDraft><Content><Paragraph",
        "<Screenplay><Scene>Not FinalDraft</Scene></Screenplay>",
        b"\xff\xfe<FinalDraft/>",
    ],
)
def test_f2_fdx_rejects_malformed_truncated_and_non_fdx_xml(
    bad_content: bytes | str,
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.parsers.fdx import FdxParser

    raw = RawScript(content=bad_content, content_type="fdx", metadata=sample_metadata())
    with pytest.raises((ValueError, expat.ExpatError, ET.ParseError)):
        FdxParser().parse(raw)


def test_f2_fdx_empty_content_prologue_escaping_unicode_and_orphaned_dual(
    sample_metadata: Callable[..., ScriptMetadata],
) -> None:
    from rtfs.exporters.fdx_exp import export_fdx
    from rtfs.parsers.fdx import FdxParser

    parser = FdxParser()
    meta = sample_metadata(title="Edge Script", writers=[])

    empty_xml = (
        '<FinalDraft DocumentType="Script" Template="No" Version="5">'
        "<Content/></FinalDraft>"
    )
    empty_doc = parser.parse(RawScript(content=empty_xml, content_type="fdx", metadata=meta))
    assert empty_doc.scenes == []

    prologue_xml = (
        '<FinalDraft DocumentType="Script" Template="No" Version="5">'
        "<Content>"
        '<Paragraph Type="Action"><Text>Cold open.</Text></Paragraph>'
        '<Paragraph Type="Character"><Text>VOICE</Text></Paragraph>'
        '<Paragraph Type="Dialogue"><Text>Listen closely.</Text></Paragraph>'
        "</Content>"
        "</FinalDraft>"
    )
    prologue_doc = parser.parse(RawScript(content=prologue_xml, content_type="fdx", metadata=meta))
    assert len(prologue_doc.scenes) == 1
    assert prologue_doc.scenes[0].heading == "PROLOGUE"
    assert isinstance(prologue_doc.scenes[0].elements[0], Action)
    assert isinstance(prologue_doc.scenes[0].elements[1], Dialogue)

    special_doc = ScriptDocument(
        metadata=meta,
        scenes=[
            Scene(
                scene_number=1,
                heading="EXT. CAFÉ — 日本語 - NIGHT",
                elements=[
                    Action(text='Symbols: & < > " \' — 日本語'),
                    Dialogue(character="RENÉ", lines='Wait & see <"ok">!', dual=True),
                ],
            )
        ],
    )
    exported = export_fdx(special_doc)
    ET.fromstring(exported)
    reparsed = parser.parse(RawScript(content=exported, content_type="fdx", metadata=meta))
    assert reparsed.scenes[0].elements[0] == Action(text='Symbols: & < > " \' — 日本語')
    assert isinstance(reparsed.scenes[0].elements[1], Dialogue)
    assert reparsed.scenes[0].elements[1].character == "RENÉ"
    assert reparsed.scenes[0].elements[1].lines == 'Wait & see <"ok">!'


# ---------------------------------------------------------------------------
# F3: DNS resolution pinning boundaries (Tier 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip_str",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "100.127.255.254",
        "0.0.0.0",
        "192.0.2.1",
        "224.0.0.1",
    ],
)
def test_f3_blocks_loopback_rfc1918_link_local_cgnat_and_special_ipv4(ip_str: str) -> None:
    from rtfs.core.http import is_public_ip, validate_public_http_url

    assert is_public_ip(ipaddress.ip_address(ip_str)) is False
    with pytest.raises(ValueError):
        validate_public_http_url(f"http://{ip_str}/secret")


def test_f3_blocks_ipv4_mapped_and_non_public_ipv6_while_allowing_mapped_public() -> None:
    from rtfs.core.http import is_public_ip, validate_public_http_url

    blocked_v6 = [
        "::1",
        "::",
        "fc00::1",
        "fd12:3456:789a::1",
        "fe80::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:100.64.0.1",
        "::ffff:169.254.169.254",
    ]
    for ip_str in blocked_v6:
        assert is_public_ip(ipaddress.ip_address(ip_str)) is False
        with pytest.raises(ValueError):
            validate_public_http_url(f"http://[{ip_str}]/")

    assert is_public_ip(ipaddress.ip_address("::ffff:93.184.216.34")) is True
    assert (
        validate_public_http_url("http://[::ffff:93.184.216.34]/ok")
        == "http://[::ffff:93.184.216.34]/ok"
    )


@pytest.mark.parametrize(
    "dns_answer",
    [
        ["93.184.216.34", "10.0.0.1"],
        ["127.0.0.1", "93.184.216.34"],
        ["93.184.216.34", "::ffff:10.0.0.1"],
    ],
)
async def test_f3_blocks_mixed_public_and_private_dns_answer_fail_closed(
    dns_answer: list[str],
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network()
    async with HttpClient(
        max_retries=2,
        min_interval=0.0,
        backoff_base=0.0,
        resolver=make_addrinfo_resolver(dns_answer),
    ) as client:
        with pytest.raises(ValueError, match="Blocked non-public IP"):
            await client.get_text("https://mixed.example/script")

    assert net.connect_calls == []


async def test_f3_blocks_toctou_dns_rebinding_across_redirect_hops(
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network(
        [
            b"HTTP/1.1 302 Found\r\n"
            b"Location: https://rebind-hop.example/internal\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n\r\n"
        ]
    )
    seen_hosts: list[str] = []

    def _lookup(host: str, _port: int) -> list[str]:
        seen_hosts.append(host)
        if host == "safe.example":
            return ["93.184.216.34"]
        return ["169.254.169.254"]

    async with HttpClient(
        max_retries=3,
        min_interval=0.0,
        backoff_base=0.0,
        resolver=make_addrinfo_resolver(_lookup),
    ) as client:
        with pytest.raises(ValueError, match="Blocked non-public IP"):
            await client.get_text("https://safe.example/start")

    assert seen_hosts == ["safe.example", "rebind-hop.example"]
    assert net.connect_calls == [("93.184.216.34", 443)]


async def test_f3_blocks_empty_dns_answer(
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network()
    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=make_addrinfo_resolver([]),
    ) as client:
        with pytest.raises((ValueError, httpx.ConnectError)):
            await client.get_text("https://empty-dns.example/script")

    assert net.connect_calls == []


async def test_f3_numeric_public_ip_skips_resolver_and_pins_ipv6(
    patch_offline_network: Callable[..., Any],
    make_addrinfo_resolver: Callable[..., Callable[..., Any]],
) -> None:
    from rtfs.core.http import HttpClient

    net = patch_offline_network(
        [
            b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\nipv4",
            b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\nipv6",
        ]
    )
    resolver_calls: list[str] = []

    def _lookup(host: str, _port: int) -> list[str]:
        resolver_calls.append(host)
        return ["2606:4700:4700::1111"]

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=make_addrinfo_resolver(_lookup),
    ) as client:
        assert await client.get_text("http://93.184.216.34/script.txt") == "ipv4"
        assert resolver_calls == []
        assert await client.get_text("https://ipv6-host.example/script.txt") == "ipv6"

    assert resolver_calls == ["ipv6-host.example"]
    assert net.connect_calls == [
        ("93.184.216.34", 80),
        ("2606:4700:4700::1111", 443),
    ]
    assert net.tls_hostnames == ["ipv6-host.example"]


async def test_f3_pinned_network_backend_blocks_unix_socket() -> None:
    from rtfs.core.http import PinnedAsyncNetworkBackend

    backend = PinnedAsyncNetworkBackend()
    with pytest.raises(ValueError):
        await backend.connect_unix_socket("/var/run/docker.sock")


# ---------------------------------------------------------------------------
# F4: Cache backend info() & clear() boundaries (Tier 2)
# ---------------------------------------------------------------------------


async def test_f4_clear_empty_cache_is_idempotent_across_all_backends(
    tmp_path: Path,
    fake_redis_client_factory: Callable[..., Any],
) -> None:
    from rtfs.core.cache import (
        DiskCacheBackend,
        MemoryCacheBackend,
        NullCacheBackend,
        RedisCacheBackend,
    )

    backends = [
        MemoryCacheBackend(),
        DiskCacheBackend(tmp_path / "empty_disk"),
        NullCacheBackend(),
        RedisCacheBackend(client=fake_redis_client_factory()),
    ]
    try:
        for backend in backends:
            await backend.clear()
            await backend.clear()
            info = await backend.info()
            assert info.entries in (0, None)
    finally:
        for backend in backends:
            await backend.close()


async def test_f4_info_accuracy_after_overwrites_deletes_and_ttl_expiration(
    tmp_path: Path,
) -> None:
    from rtfs.core.cache import DiskCacheBackend, MemoryCacheBackend

    mem = MemoryCacheBackend()
    await mem.set("k1", b"1234")
    await mem.set("k1", b"12345678")
    await mem.set("k2", b"ab")
    await mem.delete("k2")
    await mem.set("expired", b"gone", ttl=0)
    await asyncio.sleep(0.05)

    mem_info = await mem.info()
    assert mem_info.entries == 1
    assert mem_info.size_bytes == 8

    disk = DiskCacheBackend(tmp_path / "ttl_disk")
    try:
        await disk.set("k1", b"1234")
        await disk.set("k1", b"12345678")
        await disk.set("k2", b"ab")
        await disk.delete("k2")
        await disk.set("expired", b"gone", ttl=0)
        await asyncio.sleep(0.05)

        disk_info = await disk.info()
        assert disk_info.entries == 1
        assert disk_info.size_bytes is not None and disk_info.size_bytes > 0
    finally:
        await disk.close()


async def test_f4_null_cache_remains_empty_after_set_delete_clear() -> None:
    from rtfs.core.cache import NullCacheBackend

    cache = NullCacheBackend()
    await cache.set("k1", b"value", ttl=60)
    assert await cache.get("k1") is None
    await cache.delete("k1")
    await cache.clear()

    info = await cache.info()
    assert info.backend == "null"
    assert info.location is None
    assert info.entries == 0
    assert info.size_bytes == 0


async def test_f4_disk_cache_persists_entries_and_info_across_reinstantiation(
    tmp_path: Path,
) -> None:
    from rtfs.core.cache import DiskCacheBackend

    cache_dir = tmp_path / "persistent_disk"
    first = DiskCacheBackend(cache_dir)
    await first.set("one", b"payload-1")
    await first.set("two", b"payload-2")
    await first.close()

    reopened = DiskCacheBackend(cache_dir)
    try:
        info = await reopened.info()
        assert info.backend == "disk"
        assert info.location == str(cache_dir)
        assert info.entries == 2
        assert await reopened.get("one") == b"payload-1"

        await reopened.clear()
        cleared = await reopened.info()
        assert cleared.entries == 0
        assert cleared.size_bytes is not None and cleared.size_bytes >= 0
    finally:
        await reopened.close()


async def test_f4_redis_cache_prefix_isolation_credential_redaction_and_info_error(
    fake_redis_client_factory: Callable[..., Any],
) -> None:
    from rtfs.core.cache import RedisCacheBackend

    fake_client = fake_redis_client_factory()
    fake_client.store["other:keep"] = (b"stay", None)
    fake_client.store["rtfs_other:keep"] = (b"stay2", None)

    backend = RedisCacheBackend(
        url="redis://alice:s3cr3t@redis.example.com:6379/1",
        prefix="rtfs:",
        client=fake_client,
    )
    await backend.set("a", b"alpha")
    await backend.set("b", b"beta")

    info = await backend.info()
    assert info.entries == 2
    assert info.location is not None
    assert "alice" not in info.location
    assert "s3cr3t" not in info.location
    assert "redis.example.com:6379/1" in info.location

    await backend.clear()
    assert fake_client.flushdb_called is False
    assert fake_client.store["other:keep"] == (b"stay", None)
    assert fake_client.store["rtfs_other:keep"] == (b"stay2", None)
    assert (await backend.info()).entries == 0

    failing_client = fake_redis_client_factory(fail_info=True)
    failing_backend = RedisCacheBackend(
        url="redis://localhost:6379/0",
        prefix="rtfs:",
        client=failing_client,
    )
    await failing_backend.set("x", b"1")
    degraded = await failing_backend.info()
    assert degraded.entries == 1
    assert degraded.size_bytes is None


async def test_f4_redis_cache_paginated_scan_str_values_and_create_cache_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_redis_client_factory: Callable[..., Any],
) -> None:
    from rtfs.core.cache import DiskCacheBackend, RedisCacheBackend

    fake_client = fake_redis_client_factory(scan_page_size=2)
    backend = RedisCacheBackend(prefix="rtfs:", client=fake_client)

    for idx in range(5):
        await backend.set(f"k{idx}", f"val-{idx}".encode())

    assert (await backend.info()).entries == 5
    await backend.clear()
    assert (await backend.info()).entries == 0

    fake_client.store["rtfs:str_key"] = ("hello-str", None)
    assert await backend.get("str_key") == b"hello-str"

    env_dir = tmp_path / "env_cache_dir"
    monkeypatch.setenv("RTFS_CACHE_URL", f"disk://{env_dir}")
    env_cache = create_cache(None)
    try:
        assert isinstance(env_cache, DiskCacheBackend)
        assert (await env_cache.info()).location == str(env_dir)
    finally:
        await env_cache.close()
