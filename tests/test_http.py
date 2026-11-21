from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from rtfs.core.http import HttpClient


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
