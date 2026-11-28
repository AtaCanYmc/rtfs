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
