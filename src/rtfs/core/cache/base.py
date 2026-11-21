from __future__ import annotations

import base64
import hashlib
import json
from typing import Protocol, runtime_checkable

from rtfs.core.models import RawScript, SearchResult


@runtime_checkable
class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def close(self) -> None: ...


def make_cache_key(namespace: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


def encode_search_results(results: list[SearchResult]) -> bytes:
    payload = [r.model_dump(mode="json") for r in results]
    return json.dumps(payload).encode("utf-8")


def decode_search_results(data: bytes) -> list[SearchResult]:
    payload = json.loads(data.decode("utf-8"))
    return [SearchResult.model_validate(item) for item in payload]


def encode_raw_script(raw: RawScript) -> bytes:
    is_bytes = isinstance(raw.content, bytes)
    content_str = (
        base64.b64encode(raw.content).decode("ascii")
        if is_bytes
        else str(raw.content)
    )
    envelope = {
        "is_bytes": is_bytes,
        "content": content_str,
        "content_type": raw.content_type,
        "metadata": raw.metadata.model_dump(mode="json"),
    }
    return json.dumps(envelope).encode("utf-8")


def decode_raw_script(data: bytes) -> RawScript:
    envelope = json.loads(data.decode("utf-8"))
    content: bytes | str = (
        base64.b64decode(envelope["content"].encode("ascii"))
        if envelope["is_bytes"]
        else envelope["content"]
    )
    return RawScript.model_validate(
        {
            "content": content,
            "content_type": envelope["content_type"],
            "metadata": envelope["metadata"],
        }
    )
