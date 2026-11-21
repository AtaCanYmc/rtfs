from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rtfs.core.aggregator import (
    ScriptAggregator,
    filter_scenes,
    parse_file,
    parse_scene_range,
)
from rtfs.core.cache import create_cache
from rtfs.core.models import ScriptDocument, SearchResult
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.exporters.fountain_exp import export_fountain, export_txt
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.stats_exp import compute_stats

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

VALID_EXPORT_FORMATS = {"json", "fountain", "txt", "fdx"}
FORMAT_EXTENSIONS = {
    "json": ".json",
    "fountain": ".fountain",
    "txt": ".txt",
    "fdx": ".fdx",
}
SLUG_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _resolve_cache_url(cache_url: str | None, no_cache: bool) -> str | None:
    if no_cache:
        return "none://"
    return cache_url


def _render_document(doc: ScriptDocument, fmt: str) -> str:
    fmt_lower = fmt.lower().strip()
    if fmt_lower not in VALID_EXPORT_FORMATS:
        raise ValueError(
            f"Invalid format '{fmt}'. Choose from: json, fountain, txt, fdx"
        )
    if fmt_lower == "json":
        return export_json(doc)
    if fmt_lower == "fountain":
        return export_fountain(doc)
    if fmt_lower == "fdx":
        return export_fdx(doc)
    return export_txt(doc)


def _build_candidates_table(query: str, results: list[SearchResult]) -> Table:
    table = Table(title=f"Search Results: '{query}'")
    table.add_column("Index", justify="right", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold white")
    table.add_column("Type", style="magenta")
    table.add_column("Source", style="green")
    table.add_column("Format", style="yellow")
    table.add_column("Score", justify="right", style="dim")

    for idx, item in enumerate(results, start=1):
        title_label = f"{item.title} ({item.year})" if item.year else item.title
        table.add_row(
            str(idx),
            title_label,
            item.media_type,
            item.source,
            item.format,
            f"{item.score:.1f}",
        )
    return table


def _prompt_candidate_index(max_index: int) -> int:
    raw = typer.prompt(f"Select candidate [1-{max_index}]", default="1")
    try:
        choice = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid selection '{raw}': expected an integer 1..{max_index}") from exc
    if not (1 <= choice <= max_index):
        raise ValueError(f"Selection {choice} out of range (1..{max_index})")
    return choice


async def _run_search(
    query: str,
    source: str,
    allow_transcript: bool,
    cache_url: str | None,
) -> None:
    async with ScriptAggregator(cache=cache_url) as agg:
        results = await agg.search(query, source=source, allow_transcript=allow_transcript)

    if not results:
        err_console.print(f"[yellow]No scripts found for query:[/yellow] {query}")
        raise typer.Exit(code=1)

    console.print(_build_candidates_table(query, results))


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
        resolved_cache = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(_run_search(query, source, allow_transcript, resolved_cache))
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

    if scene_range is not None and scene_range.strip():
        parse_scene_range(scene_range)

    async with ScriptAggregator(cache=cache_url) as agg:
        if interactive and not query_or_url.startswith(("http://", "https://")):
            results = await agg.search(
                query_or_url,
                source=source,
                allow_transcript=allow_transcript,
            )
            if not results and not allow_transcript and source == "all":
                results = await agg.search(query_or_url, source="all", allow_transcript=True)
            if not results:
                raise LookupError(f"No scripts found matching '{query_or_url}'")

            err_console.print(_build_candidates_table(query_or_url, results))
            idx = _prompt_candidate_index(len(results))
            selected = results[idx - 1]
            doc = await agg.fetch_and_parse(selected)
        else:
            doc = await agg.get(
                query_or_url,
                source=source,
                allow_transcript=allow_transcript,
            )

    doc = filter_scenes(
        doc,
        character=character,
        location=location,
        scene_range=scene_range,
    )
    rendered = _render_document(doc, fmt_lower)

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
        resolved_cache = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(
            _run_get(
                query_or_url,
                fmt,
                output,
                source,
                allow_transcript,
                resolved_cache,
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
) -> None:
    """Parse a local screenplay file (.pdf, .fdx, .html, .txt) offline without provider lookup."""
    try:
        fmt_lower = fmt.lower().strip()
        if fmt_lower not in VALID_EXPORT_FORMATS:
            raise ValueError("Invalid format. Choose from: json, fountain, txt, fdx")

        explicit_type = content_type.lower().strip() if content_type else None
        if explicit_type is not None and explicit_type not in {"pdf", "fdx", "html", "text"}:
            raise ValueError("Invalid content-type. Choose from: pdf, fdx, html, text")

        doc = parse_file(
            file_path,
            title=title,
            content_type=explicit_type,  # type: ignore[arg-type]
        )
        doc = filter_scenes(
            doc,
            character=character,
            location=location,
            scene_range=scene_range,
        )
        rendered = _render_document(doc, fmt_lower)
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


async def _run_cache_info(cache_url: str | None, fmt: str) -> None:
    cache = create_cache(cache_url)
    try:
        info = await cache.info()
    finally:
        await cache.close()

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
        return

    table = Table(title="Cache Info")
    table.add_column("Property", style="cyan")
    table.add_column("Value", justify="right", style="bold white")
    table.add_row("Backend", info.backend)
    table.add_row("Location", info.location if info.location is not None else "N/A")
    table.add_row("Entries", str(info.entries) if info.entries is not None else "N/A")
    table.add_row(
        "Size (bytes)",
        str(info.size_bytes) if info.size_bytes is not None else "N/A",
    )
    console.print(table)


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
        asyncio.run(_run_cache_info(cache_url, fmt))
    except (ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


async def _run_cache_clear(cache_url: str | None) -> None:
    cache = create_cache(cache_url)
    try:
        info_before = await cache.info()
        await cache.clear()
    finally:
        await cache.close()
    loc_suffix = f" ({info_before.location})" if info_before.location else ""
    console.print(
        f"[green]Cleared {info_before.backend} cache{loc_suffix}.[/green]"
    )


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
        asyncio.run(_run_cache_clear(cache_url))
    except (ValueError, ImportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _sanitize_filename_slug(raw: str, index: int) -> str:
    slug = SLUG_SANITIZE_RE.sub("-", raw.strip().lower()).strip(".-_")
    if not slug:
        slug = f"script-{index}"
    return slug[:80]


def _read_batch_queries(queries_file: Path) -> list[str]:
    if not queries_file.exists() or not queries_file.is_file():
        raise FileNotFoundError(f"Queries file not found: {queries_file}")
    queries: list[str] = []
    for raw_line in queries_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        queries.append(stripped)
    if not queries:
        raise ValueError(f"No valid queries found in {queries_file}")
    return queries


async def _run_batch(
    queries_file: Path,
    output_dir: Path,
    fmt: str,
    concurrency: int,
    source: str,
    allow_transcript: bool,
    cache_url: str | None,
) -> None:
    fmt_lower = fmt.lower().strip()
    if fmt_lower not in VALID_EXPORT_FORMATS:
        raise ValueError("Invalid format. Choose from: json, fountain, txt, fdx")
    if concurrency < 1:
        raise ValueError("Concurrency must be >= 1")

    queries = _read_batch_queries(queries_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = FORMAT_EXTENSIONS[fmt_lower]

    sem = asyncio.Semaphore(concurrency)
    used_filenames: set[str] = set()
    filename_lock = asyncio.Lock()

    async with ScriptAggregator(cache=cache_url) as agg:

        async def _process_one(idx: int, query: str) -> tuple[str, bool, str]:
            async with sem:
                try:
                    doc = await agg.get(
                        query,
                        source=source,
                        allow_transcript=allow_transcript,
                    )
                    rendered = _render_document(doc, fmt_lower)
                    base_slug = _sanitize_filename_slug(doc.metadata.title or query, idx)
                    async with filename_lock:
                        candidate_name = f"{base_slug}{ext}"
                        if candidate_name in used_filenames:
                            candidate_name = f"{base_slug}-{idx}{ext}"
                        used_filenames.add(candidate_name)

                    dest = (output_dir / candidate_name).resolve()
                    if output_dir.resolve() not in dest.parents:
                        raise ValueError(f"Unsafe output path resolved: {dest}")
                    dest.write_text(rendered, encoding="utf-8")
                    return (query, True, str(dest))
                except Exception as exc:
                    return (query, False, str(exc))

        outcomes = await asyncio.gather(
            *[_process_one(i, q) for i, q in enumerate(queries, start=1)]
        )

    table = Table(title=f"Batch Export Summary ({len(outcomes)} queries)")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Query", style="bold white")
    table.add_column("Status", style="green")
    table.add_column("Output / Error", style="dim")

    failures = 0
    for idx, (query, ok, detail) in enumerate(outcomes, start=1):
        status_cell = "[green]OK[/green]" if ok else "[red]FAILED[/red]"
        if not ok:
            failures += 1
        table.add_row(str(idx), query, status_cell, detail)

    console.print(table)
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
        resolved_cache = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(
            _run_batch(
                queries_file=queries_file,
                output_dir=output_dir,
                fmt=fmt,
                concurrency=concurrency,
                source=source,
                allow_transcript=allow_transcript,
                cache_url=resolved_cache,
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
    async with ScriptAggregator(cache=cache_url) as agg:
        doc = await agg.get(query_or_url, source=source, allow_transcript=allow_transcript)

    stats = compute_stats(doc)

    summary = Table(title=f"Script Overview: {stats.title} ({stats.source})")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right", style="bold white")
    summary.add_row("Format", stats.format)
    summary.add_row("Total Scenes", str(stats.total_scenes))
    summary.add_row("INT. Scenes", str(stats.int_scenes))
    summary.add_row("EXT. Scenes", str(stats.ext_scenes))
    summary.add_row("INT / EXT Ratio", f"{stats.int_ext_ratio:.2f}")
    summary.add_row("Dialogue Words", str(stats.dialogue_words))
    summary.add_row("Action Words", str(stats.action_words))
    summary.add_row("Dialogue / Action Ratio", f"{stats.dialogue_to_action_ratio:.2f}")
    console.print(summary)

    char_table = Table(title="Top Speaking Characters")
    char_table.add_column("Rank", justify="right", style="cyan")
    char_table.add_column("Character", style="bold yellow")
    char_table.add_column("Dialogue Turns", justify="right", style="green")
    char_table.add_column("Words", justify="right", style="white")

    for rank, ch in enumerate(stats.top_characters, start=1):
        char_table.add_row(
            str(rank),
            ch.character,
            str(ch.dialogue_turns),
            str(ch.word_count),
        )
    console.print(char_table)


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
        resolved_cache = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(_run_stats(query_or_url, source, allow_transcript, resolved_cache))
    except (LookupError, ValueError, ImportError) as exc:
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

    resolved_cache = _resolve_cache_url(cache_url, no_cache)
    try:
        from rtfs.mcp.server import run_mcp_server

        run_mcp_server(
            transport=transport_lower,  # type: ignore[arg-type]
            host=host,
            port=port,
            cache_url=resolved_cache,
        )
    except (ImportError, ValueError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
