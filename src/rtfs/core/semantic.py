from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from rtfs.core.models import Action, Dialogue, Scene, ScriptDocument, Transition

EmbedFn = Callable[[list[str]], list[list[float]]]


def _scene_to_text(scene: Scene) -> str:
    parts = [scene.heading]
    for el in scene.elements:
        if isinstance(el, Dialogue):
            parts.append(f"{el.character}: {el.lines}")
        elif isinstance(el, (Action, Transition)):
            parts.append(el.text)
    return " ".join(parts)


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def default_embed_fn(texts: list[str]) -> list[list[float]]:
    """Embed texts using fastembed (requires pyrtfs[semantic])."""
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise ImportError(
            "Semantic search requires optional dependencies or a custom embed_fn. "
            "Install with: pip install 'pyrtfs[semantic]'"
        ) from exc

    model = TextEmbedding()
    return [list(map(float, vec)) for vec in model.embed(texts)]


def search_scenes_semantic(
    doc: ScriptDocument,
    query: str,
    *,
    top_k: int = 5,
    embed_fn: EmbedFn | None = None,
) -> list[dict[str, Any]]:
    """Rank scenes by semantic similarity to query, capped at 10 scenes per call."""
    if not doc.scenes:
        return []
    k = min(max(1, top_k), 10)
    fn = embed_fn or default_embed_fn
    scene_texts = [_scene_to_text(s) for s in doc.scenes]
    vectors = fn([query, *scene_texts])
    q_vec, s_vecs = vectors[0], vectors[1:]

    scored: list[dict[str, Any]] = []
    for scene, text, vec in zip(doc.scenes, scene_texts, s_vecs, strict=False):
        scored.append(
            {
                "scene_number": scene.scene_number,
                "heading": scene.heading,
                "score": round(_cosine_similarity(q_vec, vec), 4),
                "preview": text[:200],
            }
        )
    scored.sort(key=lambda item: float(item["score"]), reverse=True)
    return scored[:k]
