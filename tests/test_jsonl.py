from __future__ import annotations

import json

from rtfs.core.models import Action, Dialogue, Scene, ScriptDocument, ScriptMetadata
from rtfs.exporters.jsonl_exp import export_jsonl, iter_jsonl


def test_iter_jsonl_streams_element_records() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(title="Test", source="local", url="file://test.fountain"),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. LAB - DAY",
                elements=[
                    Action(text="Beakers bubble."),
                    Dialogue(character="ALICE", parenthetical="smiling", lines="Ready."),
                ],
            )
        ],
    )
    records = [json.loads(line) for line in iter_jsonl(doc)]
    assert len(records) == 2
    assert records[0]["type"] == "action"
    assert records[0]["text"] == "Beakers bubble."
    assert records[1]["type"] == "dialogue"
    assert records[1]["character"] == "ALICE"
    assert records[1]["text"] == "Ready."

    full = export_jsonl(doc)
    assert full.endswith("\n")
    assert len(full.strip().splitlines()) == 2
