from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pymupdf as fitz
import pytest
from typer.testing import CliRunner

from rtfs.cli.main import app
from rtfs.core.cache import DiskCacheBackend
from rtfs.core.models import (
    Action,
    Dialogue,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    SearchResult,
)
from rtfs.exporters.fdx_exp import export_fdx

runner = CliRunner()


def _fake_doc() -> ScriptDocument:
    return ScriptDocument(
        metadata=ScriptMetadata(
            title="The Matrix",
            year=1999,
            media_type="movie",
            writers=["Lilly Wachowski", "Lana Wachowski"],
            source="scriptslug",
            format="screenplay",
            url="https://www.scriptslug.com/script/the-matrix-1999",
        ),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. HEART O' THE CITY HOTEL - NIGHT",
                location="HEART O' THE CITY HOTEL",
                time_of_day="NIGHT",
                elements=[
                    Action(text="Flashlights sweep across the dark hallway."),
                    Dialogue(
                        character="TRINITY",
                        modifiers=[],
                        parenthetical=None,
                        lines="Get up, Neo.",
                    ),
                ],
            ),
            Scene(
                scene_number=2,
                heading="INT. METACORTEX CUBICLE - DAY",
                location="METACORTEX CUBICLE",
                time_of_day="DAY",
                elements=[
                    Action(text="Neo stares at a glowing monitor."),
                    Dialogue(
                        character="NEO",
                        modifiers=[],
                        parenthetical=None,
                        lines="Follow the white rabbit.",
                    ),
                ],
            ),
            Scene(
                scene_number=3,
                heading="EXT. ROOFTOP - NIGHT",
                location="ROOFTOP",
                time_of_day="NIGHT",
                elements=[
                    Dialogue(
                        character="MORPHEUS",
                        modifiers=[],
                        parenthetical=None,
                        lines="Free your mind.",
                    ),
                    Dialogue(
                        character="NEO",
                        modifiers=[],
                        parenthetical=None,
                        lines="Whoa.",
                        dual=True,
                    ),
                ],
            ),
        ],
    )


def test_cli_search_displays_results_table(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_search = AsyncMock(
        return_value=[
            SearchResult(
                title="The Matrix",
                year=1999,
                url="https://www.scriptslug.com/script/the-matrix-1999",
                source="scriptslug",
                media_type="movie",
                format="screenplay",
                score=112.0,
            )
        ]
    )
    monkeypatch.setattr("rtfs.core.aggregator.ScriptAggregator.search", mock_search)

    result = runner.invoke(app, ["search", "The Matrix", "--no-cache"])
    assert result.exit_code == 0
    assert "The Matrix (1999)" in result.stdout
    assert "scriptslug" in result.stdout


def test_cli_search_exits_1_when_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.search",
        AsyncMock(return_value=[]),
    )
    result = runner.invoke(app, ["search", "NonexistentMovie12345", "--no-cache"])
    assert result.exit_code == 1


def test_cli_get_writes_json_to_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.get",
        AsyncMock(return_value=_fake_doc()),
    )
    out_file = tmp_path / "matrix.json"
    result = runner.invoke(
        app,
        ["get", "The Matrix", "--format", "json", "--output", str(out_file), "--no-cache"],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["metadata"]["title"] == "The Matrix"
    assert len(payload["scenes"]) == 3


def test_cli_get_prints_fountain_and_fdx_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.get",
        AsyncMock(return_value=_fake_doc()),
    )
    res_fountain = runner.invoke(
        app,
        ["get", "The Matrix", "--format", "fountain", "--no-cache"],
    )
    assert res_fountain.exit_code == 0
    assert "Title: The Matrix" in res_fountain.stdout
    assert "TRINITY" in res_fountain.stdout

    res_fdx = runner.invoke(app, ["get", "The Matrix", "--format", "fdx", "--no-cache"])
    assert res_fdx.exit_code == 0
    assert "<FinalDraft" in res_fdx.stdout
    assert "<DualDialogue>" in res_fdx.stdout


def test_cli_get_interactive_candidate_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    candidates = [
        SearchResult(
            title="The Matrix",
            year=1999,
            url="https://www.scriptslug.com/script/the-matrix-1999",
            source="scriptslug",
            media_type="movie",
            format="screenplay",
            score=112.0,
        ),
        SearchResult(
            title="The Matrix Reloaded",
            year=2003,
            url="https://imsdb.com/scripts/Matrix-Reloaded,-The.html",
            source="imsdb",
            media_type="movie",
            format="screenplay",
            score=98.0,
        ),
    ]
    reloaded_doc = _fake_doc().model_copy(
        update={
            "metadata": _fake_doc().metadata.model_copy(
                update={"title": "The Matrix Reloaded", "year": 2003}
            )
        }
    )
    mock_search = AsyncMock(return_value=candidates)
    mock_fetch_and_parse = AsyncMock(return_value=reloaded_doc)

    monkeypatch.setattr("rtfs.core.aggregator.ScriptAggregator.search", mock_search)
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.fetch_and_parse",
        mock_fetch_and_parse,
    )

    result = runner.invoke(
        app,
        ["get", "Matrix", "--interactive", "--format", "json", "--no-cache"],
        input="2\n",
    )
    assert result.exit_code == 0
    mock_fetch_and_parse.assert_awaited_once_with(candidates[1])
    assert '"title": "The Matrix Reloaded"' in result.stdout

    # Out-of-range selection exits 1
    bad_choice = runner.invoke(
        app,
        ["get", "Matrix", "--interactive", "--no-cache"],
        input="99\n",
    )
    assert bad_choice.exit_code == 1


def test_cli_get_scene_level_filtering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.get",
        AsyncMock(return_value=_fake_doc()),
    )

    # Filter by character + location + scene-range (AND logic)
    res = runner.invoke(
        app,
        [
            "get",
            "The Matrix",
            "--format",
            "json",
            "--character",
            "neo",
            "--location",
            "rooftop",
            "--scene-range",
            "2-3",
            "--no-cache",
        ],
    )
    assert res.exit_code == 0
    start_idx = res.stdout.find("{")
    data = json.loads(res.stdout[start_idx:])
    assert len(data["scenes"]) == 1
    assert data["scenes"][0]["scene_number"] == 3
    assert data["scenes"][0]["location"] == "ROOFTOP"

    # Invalid scene-range exits 1
    bad_range = runner.invoke(
        app,
        ["get", "The Matrix", "--scene-range", "5-2", "--no-cache"],
    )
    assert bad_range.exit_code == 1


def test_cli_parse_local_files_without_provider_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ensure no network/provider calls happen during rtfs parse
    fail_search = AsyncMock(side_effect=AssertionError("Provider search must not be called"))
    monkeypatch.setattr("rtfs.core.aggregator.ScriptAggregator.search", fail_search)

    # 1. Local .fdx file -> JSON
    fdx_path = tmp_path / "local_script.fdx"
    fdx_path.write_text(export_fdx(_fake_doc()), encoding="utf-8")

    res_fdx = runner.invoke(
        app,
        [
            "parse",
            str(fdx_path),
            "--format",
            "json",
            "--character",
            "trinity",
        ],
    )
    assert res_fdx.exit_code == 0
    parsed_json = json.loads(res_fdx.stdout[res_fdx.stdout.find("{") :])
    assert parsed_json["metadata"]["title"] == "The Matrix"
    assert len(parsed_json["scenes"]) == 1
    assert parsed_json["scenes"][0]["scene_number"] == 1

    # 2. Local .pdf file -> JSON
    pdf_path = tmp_path / "local_script.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "INT. LOCAL BUNKER - NIGHT")
    page.insert_text((72, 125), "A terminal blinks.")
    page.insert_text((216, 160), "OPERATOR")
    page.insert_text((144, 175), "Signal acquired.")
    pdf_path.write_bytes(doc.tobytes())
    doc.close()

    res_pdf = runner.invoke(app, ["parse", str(pdf_path), "--format", "json"])
    assert res_pdf.exit_code == 0
    pdf_data = json.loads(res_pdf.stdout[res_pdf.stdout.find("{") :])
    assert len(pdf_data["scenes"]) == 1
    assert pdf_data["scenes"][0]["location"] == "LOCAL BUNKER"

    # Missing file exits 1
    missing = runner.invoke(app, ["parse", str(tmp_path / "missing.pdf")])
    assert missing.exit_code == 1


async def _seed_disk_cache(cache_dir: Path) -> None:
    cache = DiskCacheBackend(cache_dir)
    await cache.set("k1", b"cached-payload-1")
    await cache.set("k2", b"cached-payload-2")
    await cache.close()


def test_cli_cache_info_and_clear(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cli_cache"
    asyncio.run(_seed_disk_cache(cache_dir))
    cache_uri = f"disk://{cache_dir}"

    info_res = runner.invoke(
        app,
        ["cache", "info", "--cache-url", cache_uri, "--format", "json"],
    )
    assert info_res.exit_code == 0
    info_json = json.loads(info_res.stdout[info_res.stdout.find("{") :])
    assert info_json["backend"] == "disk"
    assert info_json["entries"] == 2
    assert info_json["size_bytes"] > 0

    table_res = runner.invoke(app, ["cache", "info", "--cache-url", cache_uri])
    assert table_res.exit_code == 0
    assert "disk" in table_res.stdout

    clear_res = runner.invoke(app, ["cache", "clear", "--cache-url", cache_uri])
    assert clear_res.exit_code == 0

    after_res = runner.invoke(
        app,
        ["cache", "info", "--cache-url", cache_uri, "--format", "json"],
    )
    after_json = json.loads(after_res.stdout[after_res.stdout.find("{") :])
    assert after_json["entries"] == 0


def test_cli_batch_processes_queries_and_enforces_concurrency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries_file = tmp_path / "queries.txt"
    queries_file.write_text(
        "# Comment line\n\nThe Matrix\nInception\nArrival\nMissingScript\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "corpus"

    active_count = 0
    peak_concurrency = 0

    async def _fake_get(
        self: object,
        query_or_url: str,
        source: str = "all",
        allow_transcript: bool = False,
    ) -> ScriptDocument:
        nonlocal active_count, peak_concurrency
        active_count += 1
        peak_concurrency = max(peak_concurrency, active_count)
        await asyncio.sleep(0.02)
        active_count -= 1
        if query_or_url == "MissingScript":
            raise LookupError("Not found")
        base = _fake_doc()
        return base.model_copy(
            update={"metadata": base.metadata.model_copy(update={"title": query_or_url})}
        )

    monkeypatch.setattr("rtfs.core.aggregator.ScriptAggregator.get", _fake_get)

    res = runner.invoke(
        app,
        [
            "batch",
            str(queries_file),
            "--output-dir",
            str(out_dir),
            "--format",
            "json",
            "--concurrency",
            "2",
            "--no-cache",
        ],
    )
    assert res.exit_code == 0
    assert peak_concurrency <= 2
    assert (out_dir / "the-matrix.json").exists()
    assert (out_dir / "inception.json").exists()
    assert (out_dir / "arrival.json").exists()


def test_cli_get_rejects_invalid_format() -> None:
    result = runner.invoke(app, ["get", "The Matrix", "--format", "yaml", "--no-cache"])
    assert result.exit_code == 1


def test_cli_stats_displays_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.get",
        AsyncMock(return_value=_fake_doc()),
    )
    result = runner.invoke(app, ["stats", "The Matrix", "--no-cache"])
    assert result.exit_code == 0
    assert "Script Overview: The Matrix" in result.stdout
    assert "TRINITY" in result.stdout


def test_cli_mcp_rejects_invalid_transport() -> None:
    result = runner.invoke(app, ["mcp", "--transport", "websocket"])
    assert result.exit_code == 2
