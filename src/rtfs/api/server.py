from __future__ import annotations

import hmac
import os
import time
from collections import defaultdict, deque
from dataclasses import asdict
from typing import Any

from rtfs.core.client import RTFSClient


def _parse_api_keys(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def _verify_api_key(provided: str | None, valid_keys: set[str]) -> bool:
    if not valid_keys:
        return True
    if not provided:
        return False
    return any(hmac.compare_digest(provided, k) for k in valid_keys)


class _SlidingWindowLimiter:
    """In-memory per-client sliding-window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.max_requests <= 0:
            return True
        ts = time.monotonic() if now is None else now
        q = self._hits[key]
        cutoff = ts - self.window_seconds
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= self.max_requests:
            return False
        q.append(ts)
        return True


def _render_prometheus_metrics(
    counts: dict[tuple[str, str, int], int],
    rate_limited: int,
) -> str:
    lines = [
        "# HELP rtfs_http_requests_total Total HTTP requests handled by rtfs API.",
        "# TYPE rtfs_http_requests_total counter",
    ]
    for (method, path, status), val in sorted(counts.items()):
        lines.append(
            f'rtfs_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {val}'
        )
    lines.extend(
        [
            "# HELP rtfs_http_rate_limited_total Total requests rejected with HTTP 429.",
            "# TYPE rtfs_http_rate_limited_total counter",
            f"rtfs_http_rate_limited_total {rate_limited}",
        ]
    )
    return "\n".join(lines) + "\n"


def create_app(
    cache_url: str | None = None,
    *,
    api_keys: set[str] | None = None,
    rate_limit: int | None = None,
) -> Any:
    """Create a FastAPI application with optional API-key auth, rate limiting, and /metrics."""
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse, PlainTextResponse
        from pydantic import BaseModel
    except ImportError as exc:
        raise ImportError(
            "FastAPI is required for the HTTP API server. Install with: pip install 'pyrtfs[api]'"
        ) from exc

    valid_keys = (
        api_keys
        if api_keys is not None
        else _parse_api_keys(os.environ.get("RTFS_API_KEYS") or os.environ.get("API_KEYS"))
    )
    rpm = rate_limit if rate_limit is not None else int(os.environ.get("RTFS_RATE_LIMIT", "60"))
    limiter = _SlidingWindowLimiter(max_requests=rpm, window_seconds=60.0)
    req_counts: dict[tuple[str, str, int], int] = defaultdict(int)
    rate_limited_count = 0

    app = FastAPI(title="rtfs API", version="0.5.0")

    @app.middleware("http")
    async def _auth_rate_and_metrics(request: Request, call_next: Any) -> Any:
        nonlocal rate_limited_count
        path = request.url.path
        if path not in {"/health", "/metrics"}:
            auth_header = request.headers.get("authorization", "")
            bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None
            provided_key = request.headers.get("x-api-key") or bearer
            if not _verify_api_key(provided_key, valid_keys):
                req_counts[(request.method, path, 401)] += 1
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )

            client_id = provided_key or (request.client.host if request.client else "unknown")
            if not limiter.allow(client_id):
                rate_limited_count += 1
                req_counts[(request.method, path, 429)] += 1
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

        response = await call_next(request)
        req_counts[(request.method, path, response.status_code)] += 1
        return response

    class ParseRequest(BaseModel):
        query_or_url: str
        source: str = "all"
        allow_transcript: bool = False

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        return _render_prometheus_metrics(req_counts, rate_limited_count)

    @app.get("/search")
    async def search(
        q: str,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> list[dict[str, Any]]:
        client = RTFSClient(cache=cache_url)
        try:
            results = await client.search(q, source=source, allow_transcript=allow_transcript)
            return [r.model_dump() for r in results]
        finally:
            await client.close()

    @app.post("/parse")
    async def parse_script(req: ParseRequest) -> dict[str, Any]:
        client = RTFSClient(cache=cache_url)
        try:
            doc = await client.get_document(
                req.query_or_url,
                source=req.source,
                allow_transcript=req.allow_transcript,
            )
            return doc.model_dump()
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            await client.close()

    @app.get("/stats")
    async def stats(query_or_url: str, source: str = "all") -> dict[str, Any]:
        client = RTFSClient(cache=cache_url)
        try:
            res = await client.stats(query_or_url, source=source)
            return asdict(res)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            await client.close()

    return app
