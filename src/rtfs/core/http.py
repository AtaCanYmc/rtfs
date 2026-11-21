from __future__ import annotations

import asyncio
import ssl
import time
from collections import defaultdict
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

from rtfs.core.network import (
    BLOCKED_HOST_SUFFIXES,
    BLOCKED_HOSTNAMES,
    AddrInfoEntry,
    DnsResolver,
    PinnedAsyncHTTPTransport,
    PinnedAsyncNetworkBackend,
    host_matches,
    is_public_ip,
    validate_public_http_url,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # 50 MB ceiling for PDF/HTML payloads

__all__ = [
    "AddrInfoEntry",
    "BLOCKED_HOSTNAMES",
    "BLOCKED_HOST_SUFFIXES",
    "DEFAULT_HEADERS",
    "DnsResolver",
    "HttpClient",
    "MAX_RESPONSE_BYTES",
    "PinnedAsyncHTTPTransport",
    "PinnedAsyncNetworkBackend",
    "host_matches",
    "is_public_ip",
    "validate_public_http_url",
]


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
