from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rtfs.core.aggregator import ScriptAggregator
from rtfs.exporters.fountain_exp import export_fountain, export_txt
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.stats_exp import compute_stats

app = typer.Typer(
    name="rtfs",
    help="Multi-Source Movie & TV Script CLI + Python SDK",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _resolve_cache_url(cache_url: str | None, no_cache: bool) -> str | None:
    if no_cache:
        return "none://"
    return cache_url


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

    console.print(table)


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
) -> None:
    fmt_lower = fmt.lower()
    if fmt_lower not in {"json", "fountain", "txt"}:
        raise ValueError("Invalid format. Choose from: json, fountain, txt")

    async with ScriptAggregator(cache=cache_url) as agg:
        doc = await agg.get(query_or_url, source=source, allow_transcript=allow_transcript)

    if fmt_lower == "json":
        rendered = export_json(doc)
    elif fmt_lower == "fountain":
        rendered = export_fountain(doc)
    else:
        rendered = export_txt(doc)

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
        typer.Option("--format", "-f", help="Export format: json|fountain|txt"),
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
    """Fetch, parse, and export a screenplay or transcript."""
    try:
        resolved_cache = _resolve_cache_url(cache_url, no_cache)
        asyncio.run(_run_get(query_or_url, fmt, output, source, allow_transcript, resolved_cache))
    except (LookupError, ValueError, ImportError) as exc:
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


if __name__ == "__main__":
    app()
