from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rtfs.cli.formatting import (
    build_batch_summary_table,
    build_cache_info_table,
    build_candidates_table,
    build_stats_tables,
)
from rtfs.core.client import VALID_EXPORT_FORMATS, RTFSClient, render_document

app = typer.Typer(
    name="rtfs",
    help="Multi-Source Movie & TV Script CLI + Python SDK",
    no_args_is_help=True,
)
cache_app = typer.Typer(
    name="cache",
    help="Inspect or clear the rtfs script cache.",
    no_args_is_help=True,
)
app.add_typer(cache_app, name="cache")

console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version

        typer.echo(f"rtfs {version('pyrtfs')}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show rtfs version and exit.",
        ),
    ] = False,
) -> None:
    """Multi-Source Movie & TV Script CLI + Python SDK."""


def _resolve_cache_url(cache_url: str | None, no_cache: bool) -> str | None:
    return "none://" if no_cache else cache_url


def _prompt_candidate_index(max_index: int) -> int:
    raw = typer.prompt(f"Select candidate [1-{max_index}]", default="1")
    try:
        choice = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(
            f"Invalid selection '{raw}': expected an integer 1..{max_index}"
        ) from exc
    if not (1 <= choice <= max_index):
        raise ValueError(f"Selection {choice} out of range (1..{max_index})")
    return choice


async def _run_search(
    query: str,
    source: str,
    allow_transcript: bool,
    cache_url: str | None,
) -> None:
    async with RTFSClient(cache=cache_url) as client:
        results = await client.search(
            query,
            source=source,
            allow_transcript=allow_transcript,
        )
    if not results:
        err_console.print(f"[yellow]No scripts found for query:[/yellow] {query}")
        raise typer.Exit(code=1)
    console.print(build_candidates_table(query, results))


@app.command("search")
def search_cmd(
    query: Annotated[str, typer.Argument(help="Movie or TV title to search for")],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Provider filter: all|imsdb|scriptslug|tvwriting|subslikescript",
        ),
    ] = "all",
    allow_transcript: Annotated[
        bool,
        typer.Option("--allow-transcript", help="Include transcript fallback sources"),
    ] = False,
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable caching (shorthand for none://)"),
    ] = False,
) -> None:
    """Search across script providers and rank results."""
    try:
        resolved = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(_run_search(query, source, allow_transcript, resolved))
    except (ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=2) from exc


async def _run_get(
    query_or_url: str,
    fmt: str,
    output: Path | None,
    source: str,
    allow_transcript: bool,
    cache_url: str | None,
    interactive: bool = False,
    character: str | None = None,
    location: str | None = None,
    scene_range: str | None = None,
) -> None:
    fmt_lower = fmt.lower().strip()
    if fmt_lower not in VALID_EXPORT_FORMATS:
        raise ValueError("Invalid format. Choose from: json, fountain, txt, fdx")

    async with RTFSClient(cache=cache_url) as client:
        selected = None
        if interactive and not query_or_url.startswith(("http://", "https://")):
            results = await client.search_with_fallback(
                query_or_url,
                source=source,
                allow_transcript=allow_transcript,
            )
            if not results:
                raise LookupError(f"No scripts found matching '{query_or_url}'")
            err_console.print(build_candidates_table(query_or_url, results))
            idx = _prompt_candidate_index(len(results))
            selected = results[idx - 1]

        doc = await client.get_document(
            query_or_url,
            source=source,
            allow_transcript=allow_transcript,
            selected_result=selected,
            character=character,
            location=location,
            scene_range=scene_range,
        )

    rendered = render_document(doc, fmt_lower)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        err_console.print(
            f"[green]Saved {doc.metadata.title} ({fmt_lower}) to {output}[/green]"
        )
    else:
        typer.echo(rendered, nl=False)


@app.command("get")
def get_cmd(
    query_or_url: Annotated[str, typer.Argument(help="Title query or direct script URL")],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format: json|fountain|txt|fdx"),
    ] = "fountain",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (stdout if omitted)"),
    ] = None,
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Provider filter: all|imsdb|scriptslug|tvwriting|subslikescript",
        ),
    ] = "all",
    allow_transcript: Annotated[
        bool,
        typer.Option("--allow-transcript", help="Allow transcript fallback sources"),
    ] = False,
    mermaid: Annotated[
        bool,
        typer.Option("--mermaid", help="Output character interaction & pacing Mermaid diagrams"),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            "-i",
            help="Interactively select from ranked search candidates before downloading",
        ),
    ] = False,
    character: Annotated[
        str | None,
        typer.Option("--character", help="Filter scenes containing dialogue by character"),
    ] = None,
    location: Annotated[
        str | None,
        typer.Option("--location", help="Filter scenes matching location/heading substring"),
    ] = None,
    scene_range: Annotated[
        str | None,
        typer.Option("--scene-range", help="Filter 1-indexed scene range (e.g. '1-5' or '3')"),
    ] = None,
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable caching (shorthand for none://)"),
    ] = False,
) -> None:
    """Fetch, parse, filter, and export a screenplay or transcript."""
    try:
        resolved = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(
            _run_get(
                query_or_url,
                fmt,
                output,
                source,
                allow_transcript,
                resolved,
                interactive=interactive,
                character=character,
                location=location,
                scene_range=scene_range,
            )
        )
    except (LookupError, ValueError, ImportError, typer.Abort) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("parse")
def parse_cmd(
    file_path: Annotated[Path, typer.Argument(help="Local script file (.pdf, .fdx, .html, .txt)")],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format: json|fountain|txt|fdx"),
    ] = "fountain",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (stdout if omitted)"),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Override inferred script title"),
    ] = None,
    content_type: Annotated[
        str | None,
        typer.Option("--content-type", "--type", help="Explicit parser type: pdf|fdx|html|text"),
    ] = None,
    character: Annotated[
        str | None,
        typer.Option("--character", help="Filter scenes containing dialogue by character"),
    ] = None,
    location: Annotated[
        str | None,
        typer.Option("--location", help="Filter scenes matching location/heading substring"),
    ] = None,
    scene_range: Annotated[
        str | None,
        typer.Option("--scene-range", help="Filter 1-indexed scene range (e.g. '1-5' or '3')"),
    ] = None,
    ocr: Annotated[
        bool,
        typer.Option("--ocr", help="Enable Tesseract OCR for scanned PDFs (pyrtfs[ocr])"),
    ] = False,
) -> None:
    """Parse a local screenplay file (.pdf, .fdx, .html, .txt) offline without provider lookup."""
    try:
        fmt_lower = fmt.lower().strip()
        if fmt_lower not in VALID_EXPORT_FORMATS:
            raise ValueError("Invalid format. Choose from: json, fountain, txt, fdx")

        explicit_type = content_type.lower().strip() if content_type else None
        valid_types = {"pdf", "fdx", "html", "text", "fountain"}
        if explicit_type is not None and explicit_type not in valid_types:
            raise ValueError("Invalid content-type. Choose from: pdf, fdx, html, text, fountain")

        client = RTFSClient(cache="none://")
        doc = client.parse_local(
            file_path,
            title=title,
            content_type=explicit_type,  # type: ignore[arg-type]
            character=character,
            location=location,
            scene_range=scene_range,
        )
        rendered = render_document(doc, fmt_lower)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
            err_console.print(
                f"[green]Saved {doc.metadata.title} ({fmt_lower}) to {output}[/green]"
            )
        else:
            typer.echo(rendered, nl=False)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@cache_app.command("info")
def cache_info_cmd(
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: table|json"),
    ] = "table",
) -> None:
    """Display active cache backend, storage location, entry count, and size."""
    try:
        info = asyncio.run(RTFSClient.inspect_cache(cache_url))
        if fmt.lower() == "json":
            typer.echo(
                json.dumps(
                    {
                        "backend": info.backend,
                        "location": info.location,
                        "entries": info.entries,
                        "size_bytes": info.size_bytes,
                    },
                    indent=2,
                )
            )
        else:
            console.print(build_cache_info_table(info))
    except (ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@cache_app.command("clear")
def cache_clear_cmd(
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Confirm clearing cache without interactive prompt"),
    ] = True,
) -> None:
    """Clear all entries from the configured cache backend."""
    _ = yes
    try:
        info_before = asyncio.run(RTFSClient.clear_cache(cache_url))
        loc_suffix = f" ({info_before.location})" if info_before.location else ""
        console.print(
            f"[green]Cleared {info_before.backend} cache{loc_suffix}.[/green]"
        )
    except (ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


async def _run_batch(
    queries_file: Path,
    output_dir: Path,
    fmt: str,
    concurrency: int,
    source: str,
    allow_transcript: bool,
    cache_url: str | None,
) -> None:
    async with RTFSClient(cache=cache_url) as client:
        outcomes = await client.batch_export(
            queries_file=queries_file,
            output_dir=output_dir,
            fmt=fmt,
            concurrency=concurrency,
            source=source,
            allow_transcript=allow_transcript,
        )
    console.print(build_batch_summary_table(outcomes))
    failures = sum(1 for item in outcomes if not item.ok)
    if failures == len(outcomes):
        raise LookupError(f"All {failures} batch queries failed.")


@app.command("batch")
def batch_cmd(
    queries_file: Annotated[
        Path,
        typer.Argument(help="Text file containing one query or URL per line"),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory to write exported script files"),
    ],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format: json|fountain|txt|fdx"),
    ] = "fountain",
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", "-c", help="Maximum concurrent downloads/parses (>= 1)"),
    ] = 3,
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Provider filter: all|imsdb|scriptslug|tvwriting|subslikescript",
        ),
    ] = "all",
    allow_transcript: Annotated[
        bool,
        typer.Option("--allow-transcript", help="Allow transcript fallback sources"),
    ] = False,
    mermaid: Annotated[
        bool,
        typer.Option("--mermaid", help="Output character interaction & pacing Mermaid diagrams"),
    ] = False,
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable caching (shorthand for none://)"),
    ] = False,
) -> None:
    """Batch fetch, parse, and export multiple queries from a file with concurrency limits."""
    try:
        resolved = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(
            _run_batch(
                queries_file=queries_file,
                output_dir=output_dir,
                fmt=fmt,
                concurrency=concurrency,
                source=source,
                allow_transcript=allow_transcript,
                cache_url=resolved,
            )
        )
    except (FileNotFoundError, LookupError, ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


async def _run_stats(
    query_or_url: str,
    source: str,
    allow_transcript: bool,
    cache_url: str | None,
) -> None:
    async with RTFSClient(cache=cache_url) as client:
        stats = await client.stats(
            query_or_url,
            source=source,
            allow_transcript=allow_transcript,
        )
    summary_tbl, char_tbl = build_stats_tables(stats)
    console.print(summary_tbl)
    console.print(char_tbl)


@app.command("stats")
def stats_cmd(
    query_or_url: Annotated[str, typer.Argument(help="Title query or direct script URL")],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="Provider filter: all|imsdb|scriptslug|tvwriting|subslikescript",
        ),
    ] = "all",
    allow_transcript: Annotated[
        bool,
        typer.Option("--allow-transcript", help="Allow transcript fallback sources"),
    ] = False,
    mermaid: Annotated[
        bool,
        typer.Option("--mermaid", help="Output character interaction & pacing Mermaid diagrams"),
    ] = False,
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable caching (shorthand for none://)"),
    ] = False,
) -> None:
    """Compute and display scene and character dialogue analytics."""
    try:
        resolved = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(_run_stats(query_or_url, source, allow_transcript, resolved))
    except (LookupError, ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("diff")
def diff_cmd(
    script_a: Annotated[Path, typer.Argument(help="Path to first local script")],
    script_b: Annotated[Path, typer.Argument(help="Path to second local script")],
) -> None:
    """Compare two local scripts at the scene and dialogue level."""
    try:
        client = RTFSClient(cache="none://")
        doc_a = client.parse_local(script_a)
        doc_b = client.parse_local(script_b)
        from rtfs.core.diff import diff_documents

        output = diff_documents(doc_a, doc_b)
        if output:
            typer.echo(output)
        else:
            err_console.print("[dim]No scene or dialogue differences found.[/dim]")
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("schema")
def schema_cmd() -> None:
    """Print the ScriptDocument JSON Schema."""
    import json

    from rtfs.core.models import ScriptDocument

    typer.echo(json.dumps(ScriptDocument.model_json_schema(), indent=2))


@app.command("serve")
def serve_cmd(
    host: Annotated[str, typer.Option("--host", help="Bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Bind port")] = 8000,
    cache_url: Annotated[str | None, typer.Option("--cache-url", help="Cache backend URI")] = None,
) -> None:
    """Start the optional FastAPI HTTP server (requires pyrtfs[api])."""
    try:
        import uvicorn

        from rtfs.api.server import create_app

        uvicorn.run(create_app(cache_url=cache_url), host=host, port=port)
    except ImportError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("view")
def view_cmd(
    script_path: Annotated[Path, typer.Argument(help="Path to local script")],
    diff: Annotated[
        Path | None,
        typer.Option("--diff", help="Optional second script for diff"),
    ] = None,
    character: Annotated[
        str | None,
        typer.Option("--character", help="Highlight dialogue by character"),
    ] = None,
) -> None:
    """Open an interactive terminal screenplay viewer (requires pyrtfs[tui])."""
    try:
        from rtfs.cli.tui import launch_viewer

        client = RTFSClient(cache="none://")
        doc = client.parse_local(script_path)
        diff_doc = client.parse_local(diff) if diff is not None else None
        launch_viewer(doc, diff_doc=diff_doc, highlight_character=character)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("mcp")
def mcp_cmd(
    transport: Annotated[
        str,
        typer.Option("--transport", "-t", help="MCP transport: stdio|sse"),
    ] = "stdio",
    host: Annotated[
        str,
        typer.Option("--host", help="Bind host when using SSE transport"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Bind port when using SSE transport"),
    ] = 8000,
    cache_url: Annotated[
        str | None,
        typer.Option(
            "--cache-url",
            help="Cache URI (disk://, redis://, memory://, none://); overrides RTFS_CACHE_URL",
        ),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable caching (shorthand for none://)"),
    ] = False,
) -> None:
    """Start the FastMCP server for progressive screenplay exploration."""
    transport_lower = transport.lower()
    if transport_lower not in {"stdio", "sse"}:
        err_console.print("[red]Error:[/red] Invalid transport. Choose from: stdio, sse")
        raise typer.Exit(code=2)

    resolved = _resolve_cache_url(cache_url, no_cache)
    try:
        from rtfs.mcp.server import run_mcp_server

        run_mcp_server(
            transport=transport_lower,  # type: ignore[arg-type]
            host=host,
            port=port,
            cache_url=resolved,
        )
    except (ImportError, ValueError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
