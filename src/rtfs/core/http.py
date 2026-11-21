from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any
from urllib.parse import urljoin, urlparse

import anyio
import httpcore
import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MB ceiling for PDF/HTML payloads
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")

AddrInfoEntry = tuple[
    int,
    int,
    int,
    str,
    tuple[str, int] | tuple[str, int, int, int],
]
DnsResolver = Callable[[str, int], Awaitable[Sequence[str | AddrInfoEntry]]]


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only if ip is a globally routable unicast public IP address."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.scope_id is not None or ip.is_site_local:
            return False
        if ip.ipv4_mapped is not None:
            return is_public_ip(ip.ipv4_mapped)
    return (
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def host_matches(hostname: str, *allowed_domains: str) -> bool:
    """Return True if hostname exactly equals or is a subdomain of any allowed domain."""
    clean = hostname.lower().strip(".")
    if not clean:
        return False
    return any(
        clean == domain.lower().strip(".") or clean.endswith(f".{domain.lower().strip('.')}")
        for domain in allowed_domains
    )


def validate_public_http_url(url: str) -> str:
    """Validate that a URL uses http/https and targets a public host."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Disallowed URL scheme '{parsed.scheme}' in '{url}'")

    hostname = (parsed.hostname or "").lower().strip(".")
    if hostname.startswith("[") and hostname.endswith("]"):
        hostname = hostname[1:-1]
    if not hostname:
        raise ValueError(f"Missing hostname in URL '{url}'")

    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(BLOCKED_HOST_SUFFIXES):
        raise ValueError(f"Blocked internal/local hostname '{hostname}' in '{url}'")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None and not is_public_ip(ip):
        raise ValueError(f"Blocked non-public IP address '{ip}' in '{url}'")

    return url


class PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    """Network backend that resolves DNS once, validates all IPs, and pins the TCP target."""

    def __init__(
        self,
        resolver: DnsResolver | None = None,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._inner = inner if inner is not None else httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        clean_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host

        try:
            literal_ip = ipaddress.ip_address(clean_host)
        except ValueError:
            literal_ip = None

        if literal_ip is not None:
            if not is_public_ip(literal_ip):
                raise ValueError(f"Blocked non-public IP address '{literal_ip}'")
            return await self._inner.connect_tcp(
                host=literal_ip.compressed,
                port=port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

        normalized = clean_host.lower().strip(".")
        if not normalized:
            raise ValueError("Missing hostname in TCP connection")
        if normalized in BLOCKED_HOSTNAMES or normalized.endswith(BLOCKED_HOST_SUFFIXES):
            raise ValueError(f"Blocked internal/local hostname '{normalized}'")

        try:
            with anyio.fail_after(timeout):
                if self._resolver is not None:
                    entries = await self._resolver(clean_host, port)
                else:
                    entries = await anyio.getaddrinfo(
                        clean_host, port, type=socket.SOCK_STREAM
                    )
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout(
                f"DNS resolution timed out for '{clean_host}'"
            ) from exc
        except OSError as exc:
            raise httpcore.ConnectError(
                f"DNS resolution failed for '{clean_host}': {exc}"
            ) from exc

        validated_ips: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            ip_str = entry if isinstance(entry, str) else entry[4][0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid IP address '{ip_str}' resolved for '{clean_host}'"
                ) from exc
            if not is_public_ip(ip_obj):
                raise ValueError(
                    f"Blocked non-public IP address '{ip_obj}' resolved for '{clean_host}'"
                )
            compressed = ip_obj.compressed
            if compressed not in seen:
                seen.add(compressed)
                validated_ips.append(compressed)

        if not validated_ips:
            raise httpcore.ConnectError(
                f"DNS resolution returned no addresses for '{clean_host}'"
            )

        last_exc: Exception | None = None
        for idx, pinned_ip in enumerate(validated_ips):
            try:
                return await self._inner.connect_tcp(
                    host=pinned_ip,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_exc = exc
                if idx == len(validated_ips) - 1:
                    raise

        assert last_exc is not None
        raise last_exc

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise ValueError("Unix domain sockets are not permitted for HTTP requests")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """AsyncHTTPTransport backed by PinnedAsyncNetworkBackend to prevent DNS rebinding."""

    def __init__(
        self,
        *,
        resolver: DnsResolver | None = None,
        inner_backend: httpcore.AsyncNetworkBackend | None = None,
        verify: ssl.SSLContext | str | bool = True,
        cert: Any = None,
        trust_env: bool = False,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits | None = None,
        local_address: str | None = None,
        retries: int = 0,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> None:
        resolved_limits = (
            limits
            if limits is not None
            else httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        super().__init__(
            verify=verify,
            cert=cert,
            trust_env=trust_env,
            http1=http1,
            http2=http2,
            limits=resolved_limits,
            proxy=None,
            local_address=local_address,
            retries=retries,
            socket_options=socket_options,
        )
        ssl_context = httpx.create_ssl_context(verify=verify, cert=cert, trust_env=trust_env)
        self._network_backend = PinnedAsyncNetworkBackend(
            resolver=resolver,
            inner=inner_backend,
        )
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=resolved_limits.max_connections,
            max_keepalive_connections=resolved_limits.max_keepalive_connections,
            keepalive_expiry=resolved_limits.keepalive_expiry,
            http1=http1,
            http2=http2,
            local_address=local_address,
            retries=retries,
            socket_options=socket_options,
            network_backend=self._network_backend,
        )


class HttpClient:
    """Async HTTP client with SSRF guards, size limits, rate-limiting, and backoff retries."""

    def __init__(
        self,
        timeout: float = 20.0,
        max_retries: int = 3,
        min_interval: float = 0.25,
        backoff_base: float = 0.5,
        max_redirects: int = 5,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        resolver: DnsResolver | None = None,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
        verify: ssl.SSLContext | str | bool = True,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.backoff_base = backoff_base
        self.max_redirects = max_redirects
        self.max_response_bytes = max_response_bytes
        self._resolver = resolver
        self._network_backend = network_backend
        self._verify = verify
        self._client: httpx.AsyncClient | None = None
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request: dict[str, float] = defaultdict(float)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            transport = PinnedAsyncHTTPTransport(
                resolver=self._resolver,
                inner_backend=self._network_backend,
                verify=self._verify,
                trust_env=False,
            )
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            )
        return self._client

    async def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        # ponytail: per-host lock serializes same-host requests; fine for 4 providers.
        async with self._host_locks[host]:
            elapsed = time.monotonic() - self._last_request[host]
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request[host] = time.monotonic()

    def _enforce_size_limit(self, response: httpx.Response) -> None:
        content_len = response.headers.get("content-length")
        if content_len and content_len.isdigit() and int(content_len) > self.max_response_bytes:
            raise ValueError(
                f"Response Content-Length ({content_len}) exceeds limit ({self.max_response_bytes})"
            )
        if len(response.content) > self.max_response_bytes:
            size = len(response.content)
            raise ValueError(
                f"Response payload ({size} bytes) exceeds limit ({self.max_response_bytes})"
            )

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        validate_public_http_url(url)
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            current_url = url
            current_method = method
            current_kwargs = dict(kwargs)
            try:
                for _hop in range(self.max_redirects + 1):
                    validate_public_http_url(current_url)
                    await self._throttle(current_url)
                    response = await client.request(current_method, current_url, **current_kwargs)

                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            break
                        current_url = validate_public_http_url(urljoin(current_url, location))
                        if response.status_code in {301, 302, 303} and current_method == "POST":
                            current_method = "GET"
                            current_kwargs.pop("data", None)
                            current_kwargs.pop("content", None)
                        continue
                    break
                else:
                    raise httpx.TooManyRedirects(
                        f"Exceeded max_redirects ({self.max_redirects}) for '{url}'"
                    )

                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_base * (2**attempt))
                        continue
                response.raise_for_status()
                self._enforce_size_limit(response)
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.backoff_base * (2**attempt))

        assert last_exc is not None
        raise last_exc

    async def get_text(self, url: str, **kwargs: object) -> str:
        resp = await self.request("GET", url, **kwargs)
        return resp.text

    async def get_bytes(self, url: str, **kwargs: object) -> bytes:
        resp = await self.request("GET", url, **kwargs)
        return resp.content

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> HttpClient:
        await self._get_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
