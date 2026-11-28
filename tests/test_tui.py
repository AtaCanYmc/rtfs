from __future__ import annotations

import builtins
from unittest.mock import patch

import pytest

from rtfs.cli.tui import format_scene_markup, launch_viewer
from rtfs.core.models import Action, Dialogue, Scene, ScriptDocument, ScriptMetadata


def test_format_scene_markup_highlights_character() -> None:
    scene = Scene(
        scene_number=1,
        heading="INT. LAB - NIGHT",
        elements=[
            Action(text="Monitors glow."),
            Dialogue(character="ALICE (V.O.)", lines="We are in."),
            Dialogue(character="BOB", lines="Copy that."),
        ],
    )
    rendered = format_scene_markup(scene, highlight_character="alice")
    assert "INT. LAB - NIGHT" in rendered
    assert "[bold yellow]ALICE (V.O.)[/bold yellow]" in rendered
    assert "[bold cyan]BOB[/bold cyan]" in rendered


def test_launch_viewer_raises_helpful_importerror_when_textual_missing() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(title="Test", source="local", url="file://test.fountain"),
        scenes=[],
    )
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "textual" or name.startswith("textual."):
            raise ImportError("No module named 'textual'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="pyrtfs\\[tui\\]"):
            launch_viewer(doc)


def test_format_scene_markup_with_transition_and_parenthetical() -> None:
    from rtfs.core.models import Transition

    scene = Scene(
        scene_number=2,
        heading="EXT. ROOF - DAY",
        elements=[
            Dialogue(character="ALICE", parenthetical="whispering", lines="Go."),
            Transition(text="CUT TO:"),
        ],
    )
    rendered = format_scene_markup(scene)
    assert "[italic](whispering)[/italic]" in rendered
    assert "[dim]CUT TO:[/dim]" in rendered
