from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtfs.cli.main import app


def test_cli_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "rtfs " in result.stdout


def test_cli_schema_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["title"] == "ScriptDocument"
    assert "scenes" in schema["properties"]


def test_cli_parse_jsonl_format(tmp_path: Path) -> None:
    f = tmp_path / "sample.fountain"
    f.write_text("INT. LAB - DAY\n\nALICE\nHello.\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["parse", str(f), "--format", "jsonl"])
    assert result.exit_code == 0
    record = json.loads(result.stdout.strip())
    assert record["character"] == "ALICE"
    assert record["text"] == "Hello."
