from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any
from urllib.parse import urlparse

import anyio
import httpcore
import httpx

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
