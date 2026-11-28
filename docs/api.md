# HTTP API Server (`pyrtfs[api]`)

[Back to docs index](README.md)

`rtfs` includes an optional FastAPI microservice wrapper for self-hosted deployments.

## Installation

```bash
pip install "pyrtfs[api]"
```

## Starting the Server

```bash
rtfs serve --host 0.0.0.0 --port 8000 --cache-url disk://~/.cache/rtfs
```

Programmatic usage:

```python
from rtfs.api import create_app

app = create_app(cache_url="memory://")
```

## Endpoints

| Method | Path | Parameters / Body | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Returns `{"status": "ok"}`. |
| `GET` | `/metrics` | — | Prometheus text exposition metrics (`rtfs_http_requests_total`, `rtfs_http_rate_limited_total`). |
| `GET` | `/search` | `q`, `source=all`, `allow_transcript=false` | Searches configured providers and returns ranked `SearchResult` objects. |
| `POST` | `/parse` | `{"query_or_url": "...", "source": "all", "allow_transcript": false}` | Fetches and parses a script into a `ScriptDocument` JSON payload. |
| `GET` | `/stats` | `query_or_url`, `source=all` | Computes scene, dialogue/action, and normalized character statistics. |

## Docker & GHCR Deployment

Run `rtfs serve` with a `redis://` cache backend in one command:

```bash
docker compose up -d
```

Or pull the published GHCR image directly:

```bash
docker run -d -p 8000:8000 -e RTFS_CACHE_URL=memory:// ghcr.io/atacanymc/rtfs:latest
```

## Environment Variables & Error Responses

| Variable / Status | Description |
| :--- | :--- |
| `RTFS_CACHE_URL` | Cache backend URI (`disk://~/.cache/rtfs`, `redis://redis:6379/0`, `memory://`, `none://`). |
| `RTFS_API_KEYS` | Comma-separated API keys (`X-API-Key` or `Authorization: Bearer <key>`). Unset disables auth. |
| `RTFS_RATE_LIMIT` | Per-client requests per minute (default: `60`, `0` disables rate limiting). |
| `200 OK` | JSON payload (`list[SearchResult]`, `ScriptDocument`, or `ScriptStats`). |
| `401 Unauthorized` | Missing or invalid API key when `RTFS_API_KEYS` is configured. |
| `404 Not Found` | Returned by `/parse` and `/stats` when no matching script is found (`LookupError`). |
| `429 Too Many Requests` | Client exceeded `RTFS_RATE_LIMIT` requests per minute. |

## Bruno API Collection

A ready-to-run Bruno collection is included under [`bruno/`](../bruno/bruno.json) covering `/health`, `/metrics`, `/search`, `/parse`, and `/stats` with response assertions.

1. Start the server: `rtfs serve --host 127.0.0.1 --port 8000`
2. Open the `bruno/` folder in Bruno and select the `local` environment (`baseUrl: http://127.0.0.1:8000`).
3. If `RTFS_API_KEYS` is enabled, set `apiKey` in `bruno/environments/local.bru`.
