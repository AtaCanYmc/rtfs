from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from urllib.parse import urlparse

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class HttpClient:
    """Async HTTP client with per-host polite rate-limiting and exponential backoff retries."""

    def __init__(
        self,
        timeout: float = 20.0,
        max_retries: int = 3,
        min_interval: float = 0.25,
        backoff_base: float = 0.5,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.backoff_base = backoff_base
        self._client: httpx.AsyncClient | None = None
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request: dict[str, float] = defaultdict(float)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
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

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            await self._throttle(url)
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.backoff_base * (2**attempt))
                        continue
                response.raise_for_status()
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
