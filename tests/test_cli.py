from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from rtfs.cli.main import app
from rtfs.core.models import (
    Action,
    Dialogue,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    SearchResult,
)

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
            )
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


def test_cli_get_prints_fountain_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rtfs.core.aggregator.ScriptAggregator.get",
        AsyncMock(return_value=_fake_doc()),
    )
    result = runner.invoke(app, ["get", "The Matrix", "--format", "fountain", "--no-cache"])
    assert result.exit_code == 0
    assert "Title: The Matrix" in result.stdout
    assert "TRINITY" in result.stdout


def test_cli_get_rejects_invalid_format() -> None:
    result = runner.invoke(app, ["get", "The Matrix", "--format", "xml", "--no-cache"])
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
