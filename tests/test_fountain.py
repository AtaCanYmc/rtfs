from __future__ import annotations

from pathlib import Path

from rtfs.core.client import RTFSClient
from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    ScriptMetadata,
    Transition,
)
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.exporters.fountain_exp import export_fountain
from rtfs.exporters.json_exp import export_json
from rtfs.parsers.fountain import FountainParser

SAMPLE_FOUNTAIN = """Title: Test Script
Author: Jane Doe

FADE IN:

INT. DINER - NIGHT

Rain taps the window.

ALICE
(quietly)
Did you bring the drive?

BOB ^
Right here.

CUT TO:

.ROOFTOP - CONTINUOUS

> FADE OUT.
"""


def test_fountain_parser_parses_scenes_dialogue_dual_and_transitions() -> None:
    raw = RawScript(
        content=SAMPLE_FOUNTAIN,
        content_type="fountain",
        metadata=ScriptMetadata(title="Fallback", source="local", url="file://sample.fountain"),
    )
    doc = FountainParser().parse(raw)

    assert doc.metadata.title == "Test Script"
    assert doc.metadata.writers == ["Jane Doe"]
    assert len(doc.scenes) == 3

    s1 = doc.scenes[1]
    assert s1.heading == "INT. DINER - NIGHT"
    assert isinstance(s1.elements[0], Action)
    assert s1.elements[0].text == "Rain taps the window."

    d1 = s1.elements[1]
    assert isinstance(d1, Dialogue)
    assert d1.character == "ALICE"
    assert d1.parenthetical == "quietly"
    assert d1.lines == "Did you bring the drive?"
    assert d1.dual is False

    d2 = s1.elements[2]
    assert isinstance(d2, Dialogue)
    assert d2.character == "BOB"
    assert d2.dual is True

    assert isinstance(s1.elements[3], Transition)
    assert s1.elements[3].text == "CUT TO:"

    s2 = doc.scenes[2]
    assert s2.heading == "ROOFTOP - CONTINUOUS"
    assert isinstance(s2.elements[0], Transition)
    assert s2.elements[0].text == "FADE OUT."


def test_fountain_round_trip_to_fdx_json_and_fountain() -> None:
    raw = RawScript(
        content=SAMPLE_FOUNTAIN,
        content_type="fountain",
        metadata=ScriptMetadata(title="Test Script", source="local", url="file://sample.fountain"),
    )
    doc = FountainParser().parse(raw)

    fdx_xml = export_fdx(doc)
    assert "<FinalDraft" in fdx_xml
    assert "<DualDialogue>" in fdx_xml

    json_str = export_json(doc)
    assert '"heading": "INT. DINER - NIGHT"' in json_str

    fountain_out = export_fountain(doc)
    assert "INT. DINER - NIGHT" in fountain_out
    assert "BOB^" in fountain_out


def test_client_parse_local_fountain(tmp_path: Path) -> None:
    fountain_file = tmp_path / "sample.fountain"
    fountain_file.write_text(SAMPLE_FOUNTAIN, encoding="utf-8")

    client = RTFSClient(cache="none://")
    doc = client.parse_local(fountain_file)
    assert len(doc.scenes) == 3
