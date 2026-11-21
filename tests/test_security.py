from __future__ import annotations

import ipaddress
import stat
from pathlib import Path
from typing import Any

import httpcore
import pymupdf as fitz
import pytest

from rtfs.core.cache import DiskCacheBackend, NullCacheBackend
from rtfs.core.http import (
    HttpClient,
    PinnedAsyncNetworkBackend,
    host_matches,
    is_public_ip,
    validate_public_http_url,
)
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser
from rtfs.providers.imsdb import IMSDbProvider
from rtfs.providers.scriptslug import ScriptSlugProvider
from rtfs.providers.subslikescript import SubsLikeScriptProvider
from rtfs.providers.tvwriting import TVWritingProvider


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1:8080/scripts/test.html",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal.pdf",
        "http://192.168.1.1/router.pdf",
        "http://[::1]:8000/test.pdf",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://service.internal/script.pdf",
        "file:///etc/passwd",
        "ftp://imsdb.com/scripts/Matrix.html",
    ],
)
def test_validate_public_http_url_blocks_ssrf_targets(blocked_url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_http_url(blocked_url)


def test_validate_public_http_url_allows_public_https() -> None:
    url = "https://imsdb.com/scripts/Matrix,-The.html"
    assert validate_public_http_url(url) == url


async def test_http_client_rejects_ssrf_before_network_call() -> None:
    async with HttpClient() as client:
        with pytest.raises(ValueError, match="Blocked"):
            await client.get_text("http://169.254.169.254/latest/meta-data/")


def test_provider_resolve_allowed_url_enforces_domain_allowlist() -> None:
    http = HttpClient()
    cache = NullCacheBackend()

    imsdb = IMSDbProvider(http, cache)
    assert (
        imsdb.resolve_allowed_url("https://imsdb.com", "/scripts/Matrix,-The.html")
        == "https://imsdb.com/scripts/Matrix,-The.html"
    )
    # Cross-origin or internal links embedded in scraped HTML must be rejected
    assert (
        imsdb.resolve_allowed_url(
            "https://imsdb.com",
            "https://evil.example.com/scripts/Matrix.html",
        )
        is None
    )
    assert (
        imsdb.resolve_allowed_url(
            "https://imsdb.com",
            "http://127.0.0.1/scripts/Matrix.html",
        )
        is None
    )

    slug = ScriptSlugProvider(http, cache)
    assert (
        slug.resolve_allowed_url(
            "https://www.scriptslug.com",
            "https://assets.scriptslug.com/live/pdf/scripts/the-matrix-1999.pdf",
        )
        == "https://assets.scriptslug.com/live/pdf/scripts/the-matrix-1999.pdf"
    )
    assert (
        slug.resolve_allowed_url(
            "https://www.scriptslug.com",
            "https://attacker.org/the-matrix-1999.pdf",
        )
        is None
    )

    tv = TVWritingProvider(http, cache)
    assert (
        tv.resolve_allowed_url(
            "https://sites.google.com/site/tvwriting/",
            "https://drive.google.com/file/d/123/pilot.pdf",
        )
        == "https://drive.google.com/file/d/123/pilot.pdf"
    )
    assert (
        tv.resolve_allowed_url(
            "https://sites.google.com/site/tvwriting/",
            "http://169.254.169.254/pilot.pdf",
        )
        is None
    )

    subs = SubsLikeScriptProvider(http, cache)
    assert (
        subs.resolve_allowed_url("https://subslikescript.com", "/movie/Matrix-133093")
        == "https://subslikescript.com/movie/Matrix-133093"
    )
    assert (
        subs.resolve_allowed_url("https://subslikescript.com", "https://evil.com/movie/1")
        is None
    )


def test_pdf_parser_enforces_max_pages_bound() -> None:
    doc = fitz.open()
    for idx in range(5):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"INT. ROOM {idx + 1} - DAY")
        page.insert_text((72, 130), "Action line.")
    pdf_bytes = doc.tobytes()
    doc.close()

    raw = RawScript(
        content=pdf_bytes,
        content_type="pdf",
        metadata=ScriptMetadata(
            title="Bounded PDF",
            source="scriptslug",
            url="https://www.scriptslug.com/script/bounded",
        ),
    )
    parser = PdfScreenplayParser(max_pages=2)
    parsed = parser.parse(raw)
    assert len(parsed.scenes) == 2


async def test_disk_cache_directory_permissions(tmp_path: Path) -> None:
    cache_dir = tmp_path / "secure_cache"
    cache = DiskCacheBackend(path=cache_dir)
    mode = stat.S_IMODE(cache_dir.stat().st_mode)
    assert mode == 0o700
    await cache.close()


def test_host_matches_rejects_substring_spoofing() -> None:
    assert host_matches("imsdb.com", "imsdb.com") is True
    assert host_matches("www.imsdb.com", "imsdb.com") is True
    assert host_matches("assets.scriptslug.com", "scriptslug.com") is True

    # Spoofed prefix/suffix domains that would pass substring `in` checks must fail
    assert host_matches("evil-imsdb.com", "imsdb.com") is False
    assert host_matches("imsdb.com.attacker.org", "imsdb.com") is False
    assert host_matches("subslikescript.com.evil.net", "subslikescript.com") is False
    assert host_matches("", "imsdb.com") is False


@pytest.mark.parametrize(
    ("raw_ip", "expected"),
    [
        # Public IPs
        ("93.184.216.34", True),
        ("1.1.1.1", True),
        ("2606:4700:4700::1111", True),
        ("::ffff:93.184.216.34", True),
        # Loopback & unspecified
        ("127.0.0.1", False),
        ("::1", False),
        ("0.0.0.0", False),
        ("::", False),
        # RFC1918 & ULA
        ("10.0.0.1", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("fc00::1", False),
        ("fd12:3456:789a::1", False),
        # Link-local & zone-scoped
        ("169.254.169.254", False),
        ("fe80::1", False),
        ("fe80::1%eth0", False),
        ("2001:4860:4860::8888%eth0", False),
        # CGNAT (100.64.0.0/10)
        ("100.64.0.1", False),
        ("100.127.255.254", False),
        # Multicast
        ("224.0.0.1", False),
        ("239.255.255.250", False),
        ("ff02::1", False),
        ("ff0e::1", False),
        ("::ffff:224.0.0.1", False),
        # Deprecated site-local, NAT64, IPv4-compatible, 6to4, Teredo
        ("fec0::1", False),
        ("64:ff9b::127.0.0.1", False),
        ("::127.0.0.1", False),
        ("2002:7f00:0001::", False),
        ("2001::", False),
        # Documentation & benchmarking
        ("192.0.2.1", False),
        ("198.18.0.1", False),
        ("198.51.100.1", False),
        ("203.0.113.1", False),
        ("2001:db8::1", False),
        # IPv4-mapped IPv6 non-public
        ("::ffff:127.0.0.1", False),
        ("::ffff:10.0.0.1", False),
        ("::ffff:100.64.0.1", False),
        ("::ffff:169.254.169.254", False),
    ],
)
def test_is_public_ip_matrix(raw_ip: str, expected: bool) -> None:
    ip_obj = ipaddress.ip_address(raw_ip)
    assert is_public_ip(ip_obj) is expected


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://100.64.0.1/script.pdf",
        "http://224.0.0.1/script.pdf",
        "http://[ff02::1]/script.pdf",
        "http://[fec0::1]/script.pdf",
        "http://[64:ff9b::127.0.0.1]/script.pdf",
        "http://[::127.0.0.1]/script.pdf",
        "http://[::ffff:127.0.0.1]/script.pdf",
        "http://[::ffff:100.64.0.1]/script.pdf",
        "http://[2001:4860:4860::8888%25eth0]/script.pdf",
        "http://198.18.0.1/script.pdf",
        "http://192.0.2.1/script.pdf",
    ],
)
def test_validate_public_http_url_blocks_special_ip_ranges(blocked_url: str) -> None:
    with pytest.raises(ValueError, match="Blocked non-public IP"):
        validate_public_http_url(blocked_url)


def test_validate_public_http_url_allows_public_ip_literals() -> None:
    assert validate_public_http_url("https://93.184.216.34/a.html") == "https://93.184.216.34/a.html"
    assert (
        validate_public_http_url("https://[2606:4700:4700::1111]/a.html")
        == "https://[2606:4700:4700::1111]/a.html"
    )


class _SpyBackend(httpcore.AsyncMockBackend):
    def __init__(self, buffer: list[bytes] | None = None) -> None:
        super().__init__(buffer=buffer or [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"])
        self.connect_calls: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connect_calls.append((host, port))
        return await super().connect_tcp(
            host=host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


@pytest.mark.parametrize(
    "resolved_ip",
    [
        "127.0.0.1",
        "100.64.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "fec0::1",
        "::ffff:127.0.0.1",
        "::ffff:100.64.0.1",
        "64:ff9b::127.0.0.1",
    ],
)
async def test_pinned_backend_blocks_non_public_resolved_ip_before_connect(
    resolved_ip: str,
) -> None:
    inner = _SpyBackend()

    async def fake_resolver(host: str, port: int) -> list[str]:
        return [resolved_ip]

    backend = PinnedAsyncNetworkBackend(resolver=fake_resolver, inner=inner)
    with pytest.raises(ValueError, match="Blocked non-public IP"):
        await backend.connect_tcp("rebind.example.com", 443)
    assert inner.connect_calls == []


async def test_pinned_backend_fails_closed_on_mixed_public_and_private_records() -> None:
    inner = _SpyBackend()

    async def mixed_resolver(host: str, port: int) -> list[str]:
        return ["93.184.216.34", "::ffff:10.0.0.1"]

    backend = PinnedAsyncNetworkBackend(resolver=mixed_resolver, inner=inner)
    with pytest.raises(ValueError, match="Blocked non-public IP"):
        await backend.connect_tcp("dual.example.com", 443)
    assert inner.connect_calls == []


async def test_pinned_backend_blocks_unix_sockets() -> None:
    backend = PinnedAsyncNetworkBackend(inner=_SpyBackend())
    with pytest.raises(ValueError, match="Unix domain sockets"):
        await backend.connect_unix_socket("/var/run/docker.sock")


@pytest.mark.parametrize(
    "blocked_host",
    ["localhost", "LOCALHOST.", "metadata.google.internal", "db.internal"],
)
async def test_pinned_backend_blocks_internal_hostnames_before_dns(
    blocked_host: str,
) -> None:
    inner = _SpyBackend()
    called = False

    async def fail_if_called(host: str, port: int) -> list[str]:
        nonlocal called
        called = True
        return ["93.184.216.34"]

    backend = PinnedAsyncNetworkBackend(resolver=fail_if_called, inner=inner)
    with pytest.raises(ValueError, match="Blocked internal/local hostname"):
        await backend.connect_tcp(blocked_host, 80)
    assert called is False
    assert inner.connect_calls == []


async def test_http_client_ignores_proxy_env_with_trust_env_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:8888")

    inner = _SpyBackend()

    async def fake_resolver(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=fake_resolver,
        network_backend=inner,
    ) as client:
        raw_client = await client._get_client()
        assert raw_client.trust_env is False
        assert raw_client._mounts == {}
        text = await client.get_text("http://scripts.example.com/test")
        assert text == "ok"
        assert inner.connect_calls == [("93.184.216.34", 80)]

