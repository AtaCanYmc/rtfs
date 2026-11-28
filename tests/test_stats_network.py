from __future__ import annotations

from rtfs.core.models import Action, Dialogue, Scene, ScriptDocument, ScriptMetadata
from rtfs.exporters.stats_exp import compute_stats, export_stats_mermaid


def test_compute_stats_builds_interaction_matrix_and_scene_pacing() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(title="Network", source="local", url="file://net.fountain"),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. LAB - DAY",
                elements=[
                    Action(text="Machines hum."),
                    Dialogue(character="ALICE", lines="Ready?"),
                    Dialogue(character="BOB (V.O.)", lines="Always."),
                ],
            ),
            Scene(
                scene_number=2,
                heading="EXT. ROOF - NIGHT",
                elements=[
                    Dialogue(character="ALICE (CONT'D)", lines="Look."),
                    Dialogue(character="BOB", lines="Whoa."),
                    Dialogue(character="CAROL", lines="Wait."),
                ],
            ),
        ],
    )

    stats = compute_stats(doc)
    assert stats.interactions["ALICE"]["BOB"] == 2
    assert stats.interactions["BOB"]["ALICE"] == 2
    assert stats.interactions["ALICE"]["CAROL"] == 1
    assert stats.interactions["BOB"]["CAROL"] == 1

    assert len(stats.scene_pacing) == 2
    s1 = stats.scene_pacing[0]
    assert s1.scene_number == 1
    assert s1.dialogue_words == 2
    assert s1.action_words == 2
    assert s1.dialogue_density == 0.5

    mermaid = export_stats_mermaid(stats)
    assert "flowchart LR" in mermaid
    assert "ALICE ---|2| BOB" in mermaid
    assert "xychart-beta" in mermaid
