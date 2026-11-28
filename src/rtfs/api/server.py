from __future__ import annotations

from dataclasses import asdict
from typing import Any

from rtfs.core.client import RTFSClient


def create_app(cache_url: str | None = None) -> Any:
    """Create a FastAPI application exposing rtfs search, parse, and stats endpoints."""
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as exc:
        raise ImportError(
            "FastAPI is required for the HTTP API server. Install with: pip install 'pyrtfs[api]'"
        ) from exc

    app = FastAPI(title="rtfs API", version="0.5.0")

    class ParseRequest(BaseModel):
        query_or_url: str
        source: str = "all"
        allow_transcript: bool = False

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
