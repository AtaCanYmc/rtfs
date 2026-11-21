from __future__ import annotations

from rich.table import Table

from rtfs.core.cache import CacheInfo
from rtfs.core.client import BatchItemResult
from rtfs.core.models import SearchResult
from rtfs.exporters.stats_exp import ScriptStats


def build_candidates_table(query: str, results: list[SearchResult]) -> Table:
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


def build_cache_info_table(info: CacheInfo) -> Table:
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
    return table


def build_batch_summary_table(outcomes: list[BatchItemResult]) -> Table:
    table = Table(title=f"Batch Export Summary ({len(outcomes)} queries)")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Query", style="bold white")
    table.add_column("Status", style="green")
    table.add_column("Output / Error", style="dim")

    for idx, item in enumerate(outcomes, start=1):
        status_cell = "[green]OK[/green]" if item.ok else "[red]FAILED[/red]"
        table.add_row(str(idx), item.query, status_cell, item.detail)
    return table


def build_stats_tables(stats: ScriptStats) -> tuple[Table, Table]:
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
    return summary, char_table
