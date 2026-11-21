from __future__ import annotations

import socket
import ssl
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import anyio
import httpcore
import httpx
import pytest

from rtfs.core.http import HttpClient, PinnedAsyncNetworkBackend


def _make_response(
    status_code: int = 200,
    content: bytes = b"ok",
    headers: dict[str, str] | None = None,
    url: str = "https://imsdb.com/scripts/Matrix.html",
) -> httpx.Response:
    req = httpx.Request("GET", url)
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers or {},
        request=req,
    )


async def test_http_client_retries_on_transient_503_then_succeeds() -> None:
    client = HttpClient(max_retries=3, min_interval=0.0, backoff_base=0.0)
    mock_inner = AsyncMock()
    mock_inner.is_closed = False
    mock_inner.request.side_effect = [
        _make_response(status_code=503, content=b"unavailable"),
        _make_response(status_code=429, content=b"rate limited"),
        _make_response(status_code=200, content=b"EXT. CITY - NIGHT"),
    ]
    client._client = mock_inner

    text = await client.get_text("https://imsdb.com/scripts/Matrix.html")
    assert text == "EXT. CITY - NIGHT"
    assert mock_inner.request.call_count == 3


async def test_http_client_raises_after_exhausting_max_retries() -> None:
    client = HttpClient(max_retries=2, min_interval=0.0, backoff_base=0.0)
    mock_inner = AsyncMock()
    mock_inner.is_closed = False
    mock_inner.request.side_effect = httpx.ConnectTimeout("Timed out")
    client._client = mock_inner

    with pytest.raises(httpx.ConnectTimeout):
        await client.get_bytes("https://imsdb.com/scripts/Matrix.html")
    assert mock_inner.request.call_count == 2


async def test_http_client_follows_valid_redirect_and_converts_post_302_to_get() -> None:
    client = HttpClient(max_retries=1, min_interval=0.0, backoff_base=0.0)
    mock_inner = AsyncMock()
    mock_inner.is_closed = False
    mock_inner.request.side_effect = [
        _make_response(
            status_code=302,
            headers={"location": "/scripts/Matrix,-The.html"},
            url="https://imsdb.com/search.php",
        ),
        _make_response(
            status_code=200,
            content=b"<pre>INT. ROOM - DAY</pre>",
            url="https://imsdb.com/scripts/Matrix,-The.html",
        ),
    ]
    client._client = mock_inner

    resp = await client.request(
        "POST",
        "https://imsdb.com/search.php",
        data={"search_query": "Matrix"},
    )
    assert resp.status_code == 200
    assert mock_inner.request.call_count == 2
    second_call = mock_inner.request.call_args_list[1]
    assert second_call.args[0] == "GET"
    assert second_call.args[1] == "https://imsdb.com/scripts/Matrix,-The.html"
    assert "data" not in second_call.kwargs


async def test_http_client_blocks_redirect_to_internal_ip() -> None:
    client = HttpClient(max_retries=1, min_interval=0.0, backoff_base=0.0)
    mock_inner = AsyncMock()
    mock_inner.is_closed = False
    mock_inner.request.side_effect = [
        _make_response(
            status_code=302,
            headers={"location": "http://127.0.0.1:8080/internal"},
            url="https://imsdb.com/scripts/Matrix.html",
        ),
    ]
    client._client = mock_inner

    with pytest.raises(ValueError, match="Blocked non-public IP"):
        await client.get_text("https://imsdb.com/scripts/Matrix.html")


async def test_http_client_raises_on_too_many_redirects() -> None:
    client = HttpClient(max_retries=1, min_interval=0.0, backoff_base=0.0, max_redirects=2)
    mock_inner = AsyncMock()
    mock_inner.is_closed = False
    mock_inner.request.return_value = _make_response(
        status_code=302,
        headers={"location": "/loop"},
    )
    client._client = mock_inner

    with pytest.raises(httpx.TooManyRedirects):
        await client.get_text("https://imsdb.com/start")


async def test_http_client_enforces_max_response_bytes() -> None:
    client = HttpClient(max_retries=1, min_interval=0.0, max_response_bytes=16)
    mock_inner = AsyncMock()
    mock_inner.is_closed = False
    mock_inner.request.return_value = _make_response(
        status_code=200,
        content=b"x" * 32,
    )
    client._client = mock_inner

    with pytest.raises(ValueError, match="exceeds limit"):
        await client.get_bytes("https://imsdb.com/scripts/Huge.html")


class _SpyAsyncStream(httpcore.AsyncMockStream):
    def __init__(
        self,
        buffer: list[bytes],
        written: list[bytes],
        tls_hostnames: list[str | None],
    ) -> None:
        super().__init__(buffer=buffer)
        self._written = written
        self._tls_hostnames = tls_hostnames

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._written.append(buffer)

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self._tls_hostnames.append(server_hostname)
        return self


class _SpyNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        responses: list[list[bytes]] | Callable[[str, int], list[bytes]] | None = None,
        fail_hosts: dict[str, Exception] | None = None,
    ) -> None:
        self._responses = responses
        self._fail_hosts = fail_hosts or {}
        self.connect_calls: list[tuple[str, int]] = []
        self.sleep_calls: list[float] = []
        self.written: list[bytes] = []
        self.tls_hostnames: list[str | None] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connect_calls.append((host, port))
        if host in self._fail_hosts:
            raise self._fail_hosts[host]
        if callable(self._responses):
            buf = self._responses(host, port)
        elif isinstance(self._responses, list) and self._responses:
            buf = self._responses.pop(0)
        else:
            buf = [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"]
        return _SpyAsyncStream(
            buffer=list(buf),
            written=self.written,
            tls_hostnames=self.tls_hostnames,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("connect_unix_socket should never be called")

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)


async def test_http_client_pins_dns_once_and_preserves_host_and_tls_sni() -> None:
    resolver_calls: list[tuple[str, int]] = []

    async def fake_resolver(host: str, port: int) -> list[str]:
        resolver_calls.append((host, port))
        return ["93.184.216.34"]

    spy_backend = _SpyNetworkBackend(
        responses=[[b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nscript"]]
    )

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=fake_resolver,
        network_backend=spy_backend,
    ) as client:
        text = await client.get_text("https://imsdb.com/scripts/Matrix.html")

    assert text == "script"
    assert resolver_calls == [("imsdb.com", 443)]
    assert spy_backend.connect_calls == [("93.184.216.34", 443)]
    assert spy_backend.tls_hostnames == ["imsdb.com"]
    wire_request = b"".join(spy_backend.written)
    assert b"Host: imsdb.com\r\n" in wire_request


async def test_http_client_uses_anyio_getaddrinfo_when_no_resolver_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, int]] = []

    async def fake_getaddrinfo(
        host: str, port: int, *, family: int = 0, type: int = 0, proto: int = 0, flags: int = 0
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        calls.append((host, port, type))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(anyio, "getaddrinfo", fake_getaddrinfo)
    spy_backend = _SpyNetworkBackend()

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        network_backend=spy_backend,
    ) as client:
        assert await client.get_text("http://scripts.example.com/ok") == "ok"

    assert calls == [("scripts.example.com", 80, socket.SOCK_STREAM)]
    assert spy_backend.connect_calls == [("93.184.216.34", 80)]


async def test_http_client_blocks_toctou_dns_rebinding_across_connections() -> None:
    dns_snapshots = [["93.184.216.34"], ["127.0.0.1"]]
    resolver_calls = 0

    async def rebinding_resolver(host: str, port: int) -> list[str]:
        nonlocal resolver_calls
        idx = min(resolver_calls, len(dns_snapshots) - 1)
        resolver_calls += 1
        return dns_snapshots[idx]

    spy_backend = _SpyNetworkBackend(
        responses=[[b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 2\r\n\r\nok"]]
    )

    async with HttpClient(
        max_retries=3,
        min_interval=0.0,
        backoff_base=0.0,
        resolver=rebinding_resolver,
        network_backend=spy_backend,
    ) as client:
        assert await client.get_text("http://rebind.example.com/first") == "ok"
        assert resolver_calls == 1
        assert spy_backend.connect_calls == [("93.184.216.34", 80)]

        # Second request opens a fresh connection; DNS has flipped to 127.0.0.1.
        # Must fail fast with ValueError without retrying or connecting.
        with pytest.raises(ValueError, match="Blocked non-public IP"):
            await client.get_text("http://rebind.example.com/second")

    assert resolver_calls == 2
    assert spy_backend.connect_calls == [("93.184.216.34", 80)]


async def test_pinned_backend_falls_back_across_validated_public_ips_without_re_resolving() -> None:
    resolver_calls = 0

    async def multi_resolver(host: str, port: int) -> list[str]:
        nonlocal resolver_calls
        resolver_calls += 1
        return ["2606:4700:4700::1111", "93.184.216.34", "93.184.216.34"]

    spy_backend = _SpyNetworkBackend(
        fail_hosts={"2606:4700:4700::1111": httpcore.ConnectError("IPv6 unreachable")}
    )

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=multi_resolver,
        network_backend=spy_backend,
    ) as client:
        assert await client.get_text("http://dualstack.example.com/script") == "ok"

    assert resolver_calls == 1
    assert spy_backend.connect_calls == [
        ("2606:4700:4700::1111", 80),
        ("93.184.216.34", 80),
    ]


async def test_pinned_backend_handles_literal_ips_without_calling_resolver() -> None:
    async def fail_resolver(host: str, port: int) -> list[str]:
        raise AssertionError("Resolver must not be called for literal IP targets")

    spy_backend = _SpyNetworkBackend()
    backend = PinnedAsyncNetworkBackend(resolver=fail_resolver, inner=spy_backend)

    await backend.connect_tcp("93.184.216.34", 80)
    await backend.connect_tcp("[2606:4700:4700::1111]", 443)
    assert spy_backend.connect_calls == [
        ("93.184.216.34", 80),
        ("2606:4700:4700::1111", 443),
    ]

    with pytest.raises(ValueError, match="Blocked non-public IP"):
        await backend.connect_tcp("[::1]", 443)
    with pytest.raises(ValueError, match="Blocked non-public IP"):
        await backend.connect_tcp("100.64.0.1", 80)
    assert len(spy_backend.connect_calls) == 2


async def test_pinned_backend_maps_empty_oserror_timeout_and_delegates_sleep() -> None:
    spy_backend = _SpyNetworkBackend()

    async def empty_resolver(host: str, port: int) -> list[str]:
        return []

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=empty_resolver,
        network_backend=spy_backend,
    ) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get_text("http://empty.example.com/")

    async def os_error_resolver(host: str, port: int) -> list[str]:
        raise OSError("NXDOMAIN")

    async with HttpClient(
        max_retries=1,
        min_interval=0.0,
        resolver=os_error_resolver,
        network_backend=spy_backend,
    ) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get_text("http://nxdomain.example.com/")

    async def slow_resolver(host: str, port: int) -> list[str]:
        await anyio.sleep(0.2)
        return ["93.184.216.34"]

    async with HttpClient(
        timeout=0.01,
        max_retries=1,
        min_interval=0.0,
        resolver=slow_resolver,
        network_backend=spy_backend,
    ) as client:
        with pytest.raises(httpx.ConnectTimeout):
            await client.get_text("http://slowdns.example.com/")

    backend = PinnedAsyncNetworkBackend(inner=spy_backend)
    await backend.sleep(0.25)
    assert spy_backend.sleep_calls == [0.25]


async def test_http_client_blocks_redirect_to_private_resolved_domain_without_retry() -> None:
    dns_calls: list[str] = []

    async def redirect_resolver(host: str, port: int) -> list[str]:
        dns_calls.append(host)
        if host == "public.example.com":
            return ["93.184.216.34"]
        return ["10.0.0.1"]

    spy_backend = _SpyNetworkBackend(
        responses=[
            [
                b"HTTP/1.1 302 Found\r\n"
                b"Location: https://internal-rebind.example.com/secret\r\n"
                b"Content-Length: 0\r\n\r\n"
            ]
        ]
    )

    async with HttpClient(
        max_retries=3,
        min_interval=0.0,
        backoff_base=0.0,
        resolver=redirect_resolver,
        network_backend=spy_backend,
    ) as client:
        with pytest.raises(ValueError, match="Blocked non-public IP"):
            await client.get_text("https://public.example.com/start")

    assert dns_calls == ["public.example.com", "internal-rebind.example.com"]
    assert spy_backend.connect_calls == [("93.184.216.34", 443)]
