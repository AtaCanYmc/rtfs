from __future__ import annotations

import json

from rtfs.core.models import (
    Action,
    Dialogue,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    Transition,
)
from rtfs.exporters.fountain_exp import export_fountain, export_txt
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.stats_exp import compute_stats


def _sample_document() -> ScriptDocument:
    return ScriptDocument(
        metadata=ScriptMetadata(
            title="Inception",
            year=2010,
            media_type="movie",
            writers=["Christopher Nolan"],
            source="scriptslug",
            format="screenplay",
            url="https://www.scriptslug.com/script/inception-2010",
        ),
        scenes=[
            Scene(
                scene_number=1,
                heading="EXT. DAWN CRASHING SURF - DAY",
                location="DAWN CRASHING SURF",
                time_of_day="DAY",
                elements=[
                    Action(text="Waves toss a bearded man onto wet sand."),
                    Dialogue(
                        character="COBB",
                        modifiers=["V.O."],
                        parenthetical="weakly",
                        lines="What is the most resilient parasite?",
                    ),
                    Transition(text="CUT TO:"),
                ],
            ),
            Scene(
                scene_number=2,
                heading="INT. JAPANESE CASTLE DINING ROOM - NIGHT",
                location="JAPANESE CASTLE DINING ROOM",
                time_of_day="NIGHT",
                elements=[
                    Action(text="Guards escort Cobb toward an elderly host."),
                    Dialogue(
                        character="SAITO",
                        modifiers=[],
                        parenthetical=None,
                        lines="Are you here to kill me?",
                    ),
                    Dialogue(
                        character="COBB",
                        modifiers=[],
                        parenthetical=None,
                        lines="I know what this is.",
                    ),
                ],
            ),
        ],
    )


def test_export_json() -> None:
    doc = _sample_document()
    raw_json = export_json(doc)
    parsed = json.loads(raw_json)

    assert parsed["metadata"]["title"] == "Inception"
    assert len(parsed["scenes"]) == 2
    assert parsed["scenes"][0]["elements"][1]["character"] == "COBB"


def test_export_fountain() -> None:
    doc = _sample_document()
    fountain = export_fountain(doc)

    assert "Title: Inception" in fountain
    assert "Author: Christopher Nolan" in fountain
    assert "EXT. DAWN CRASHING SURF - DAY" in fountain
    assert "COBB (V.O.)" in fountain
    assert "(weakly)" in fountain
    assert "What is the most resilient parasite?" in fountain
    assert "CUT TO:" in fountain


def test_compute_stats() -> None:
    doc = _sample_document()
    stats = compute_stats(doc)

    assert stats.title == "Inception"
    assert stats.total_scenes == 2
    assert stats.int_scenes == 1
    assert stats.ext_scenes == 1
    assert stats.int_ext_ratio == 1.0
    assert stats.top_characters[0].character == "COBB"
    assert stats.top_characters[0].dialogue_turns == 2
    assert stats.top_characters[1].character == "SAITO"
    assert stats.top_characters[1].dialogue_turns == 1


def test_export_fountain_and_txt_dual_dialogue() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(
            title="Dual Test",
            source="test",
            url="https://example.com/dual",
        ),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. CONTROL ROOM - NIGHT",
                elements=[
                    Dialogue(character="ALICE", lines="Cut the wire!"),
                    Dialogue(character="BOB", lines="Don't touch it!", dual=True),
                    Dialogue(
                        character="CAROL",
                        modifiers=["V.O."],
                        parenthetical="over radio",
                        lines="Abort now!",
                        dual=True,
                    ),
                ],
            )
        ],
    )

    fountain = export_fountain(doc)
    txt = export_txt(doc)
    assert fountain == txt
    assert "\nALICE\nCut the wire!\n" in fountain
    assert "\nBOB^\nDon't touch it!\n" in fountain
    assert "\nCAROL (V.O.)^\n(over radio)\nAbort now!\n" in fountain


def test_compute_stats_counts_dual_dialogue() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(
            title="Dual Stats",
            source="test",
            url="https://example.com/dual-stats",
        ),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. ROOM - DAY",
                elements=[
                    Dialogue(character="ALICE", lines="One two three"),
                    Dialogue(character="BOB", lines="Four five", dual=True),
                ],
            )
        ],
    )

    stats = compute_stats(doc)
    assert stats.dialogue_words == 5
    by_char = {c.character: c for c in stats.top_characters}
    assert by_char["ALICE"].dialogue_turns == 1
    assert by_char["ALICE"].word_count == 3
    assert by_char["BOB"].dialogue_turns == 1
    assert by_char["BOB"].word_count == 2

