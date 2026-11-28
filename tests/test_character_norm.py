from __future__ import annotations

from rtfs.core.aggregator import filter_scenes
from rtfs.core.models import Dialogue, Scene, ScriptDocument, ScriptMetadata
from rtfs.exporters.stats_exp import compute_stats
from rtfs.parsers.base import normalize_character_name


def test_normalize_character_name_strips_parentheticals() -> None:
    assert normalize_character_name("ALICE (V.O.)") == "ALICE"
    assert normalize_character_name("ALICE (O.S.) (CONT'D)") == "ALICE"
    assert normalize_character_name("BOB ^") == "BOB"
    assert normalize_character_name("  alice (cont'd)  ") == "ALICE"


def test_stats_and_filter_scenes_normalize_character_aliases() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(title="Test", source="local", url="file://test.fountain"),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. OFFICE - DAY",
                elements=[
                    Dialogue(character="ALICE", lines="Hello there."),
                    Dialogue(character="ALICE (V.O.)", lines="Thinking aloud."),
                    Dialogue(character="ALICE (CONT'D)", lines="Still talking."),
                ],
            ),
            Scene(
                scene_number=2,
                heading="EXT. STREET - NIGHT",
                elements=[
                    Dialogue(character="BOB (O.S.)", lines="Watch out."),
                ],
            ),
        ],
    )

    stats = compute_stats(doc)
    assert len(stats.top_characters) == 2
    alice_stat = next(c for c in stats.top_characters if c.character == "ALICE")
    assert alice_stat.dialogue_turns == 3

    filtered = filter_scenes(doc, character="alice")
    assert len(filtered.scenes) == 1
    assert filtered.scenes[0].scene_number == 1

    filtered_bob = filter_scenes(doc, character="BOB (V.O.)")
    assert len(filtered_bob.scenes) == 1
    assert filtered_bob.scenes[0].scene_number == 2
