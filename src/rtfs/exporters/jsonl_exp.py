from __future__ import annotations

import json
from collections.abc import Iterator

from rtfs.core.models import Action, Dialogue, ScriptDocument, Transition


def iter_jsonl(doc: ScriptDocument) -> Iterator[str]:
    """Yield one JSON-serialized record per screenplay element for streaming pipelines."""
    title = doc.metadata.title
    source = doc.metadata.source
    for scene in doc.scenes:
        for idx, el in enumerate(scene.elements):
            record: dict[str, object] = {
                "title": title,
                "source": source,
                "scene_number": scene.scene_number,
                "heading": scene.heading,
                "element_index": idx,
                "type": el.type,
            }
            if isinstance(el, Dialogue):
                record["character"] = el.character
                record["parenthetical"] = el.parenthetical
                record["text"] = el.lines
                record["dual"] = el.dual
            elif isinstance(el, (Action, Transition)):
                record["text"] = el.text
            yield json.dumps(record, ensure_ascii=False)


def export_jsonl(doc: ScriptDocument) -> str:
    """Serialize a ScriptDocument into newline-delimited JSON (JSONL)."""
    lines = list(iter_jsonl(doc))
    return ("\n".join(lines) + "\n") if lines else ""
