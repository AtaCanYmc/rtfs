from __future__ import annotations

import builtins
from unittest.mock import patch

import pytest

from rtfs.core.models import Action, Dialogue, Scene, ScriptDocument, ScriptMetadata
from rtfs.core.semantic import default_embed_fn, search_scenes_semantic


def _fake_embed(texts: list[str]) -> list[list[float]]:
    vecs: list[list[float]] = []
    for t in texts:
        low = t.lower()
        rain = 1.0 if ("rain" in low or "storm" in low) else 0.0
        argue = 1.0 if ("argue" in low or "shout" in low or "yell" in low) else 0.0
        cafe = 1.0 if "coffee" in low else 0.0
        vecs.append([rain, argue, cafe])
    return vecs


def test_search_scenes_semantic_ranks_matching_scenes_and_caps_top_k() -> None:
    doc = ScriptDocument(
        metadata=ScriptMetadata(title="Test", source="local", url="file://test.fountain"),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. CAFE - DAY",
                elements=[Action(text="Quietly sipping coffee.")],
            ),
            Scene(
                scene_number=2,
                heading="EXT. STREET - NIGHT",
                elements=[
                    Action(text="Heavy rain pours down."),
                    Dialogue(character="ALICE", lines="Why did you shout and argue?"),
                ],
            ),
        ],
    )

    hits = search_scenes_semantic(doc, "argument in the rain", top_k=20, embed_fn=_fake_embed)
    assert len(hits) == 2
    assert hits[0]["scene_number"] == 2
    assert hits[0]["score"] > hits[1]["score"]


def test_default_embed_fn_raises_helpful_importerror_when_fastembed_missing() -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="pyrtfs\\[semantic\\]"):
            default_embed_fn(["hello"])
