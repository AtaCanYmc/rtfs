from __future__ import annotations

import difflib

from rtfs.core.models import Dialogue, ScriptDocument
from rtfs.parsers.base import normalize_character_name


def _script_lines(doc: ScriptDocument) -> list[str]:
    lines: list[str] = []
    for scene in doc.scenes:
        lines.append(scene.heading)
        for el in scene.elements:
            if isinstance(el, Dialogue):
                char = normalize_character_name(el.character)
                lines.append(f"{char}: {el.lines}")
    return lines


def diff_documents(doc_a: ScriptDocument, doc_b: ScriptDocument) -> str:
    """Return a unified diff of scene headings and dialogue lines between two scripts."""
    return "\n".join(
        difflib.unified_diff(
            _script_lines(doc_a),
            _script_lines(doc_b),
            fromfile=doc_a.metadata.title or "script_a",
            tofile=doc_b.metadata.title or "script_b",
            lineterm="",
        )
    )
