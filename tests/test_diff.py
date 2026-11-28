from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from rtfs.cli.main import app
from rtfs.core.diff import diff_documents
from rtfs.core.models import Dialogue, Scene, ScriptDocument, ScriptMetadata


def test_diff_documents_shows_scene_and_dialogue_changes() -> None:
    doc_a = ScriptDocument(
        metadata=ScriptMetadata(title="Draft 1", source="local", url="file://a.fountain"),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. CAFE - DAY",
                elements=[Dialogue(character="ALICE", lines="Coffee, please.")],
            ),
        ],
    )
    doc_b = ScriptDocument(
        metadata=ScriptMetadata(title="Draft 2", source="local", url="file://b.fountain"),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. CAFE - NIGHT",
                elements=[Dialogue(character="ALICE", lines="Tea, please.")],
            ),
        ],
    )
    diff_text = diff_documents(doc_a, doc_b)
    assert "-INT. CAFE - DAY" in diff_text
    assert "+INT. CAFE - NIGHT" in diff_text
    assert "-ALICE: Coffee, please." in diff_text
    assert "+ALICE: Tea, please." in diff_text


def test_cli_diff_command(tmp_path: Path) -> None:
    a = tmp_path / "a.fountain"
    b = tmp_path / "b.fountain"
    a.write_text("INT. ROOM - DAY\n\nALICE\nHello.\n", encoding="utf-8")
    b.write_text("INT. ROOM - NIGHT\n\nALICE\nGoodbye.\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["diff", str(a), str(b)])
    assert result.exit_code == 0
    assert "-INT. ROOM - DAY" in result.stdout
    assert "+INT. ROOM - NIGHT" in result.stdout
    assert "-ALICE: Hello." in result.stdout
    assert "+ALICE: Goodbye." in result.stdout
