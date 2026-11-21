from __future__ import annotations

from rtfs.core.models import Action, Dialogue, ScriptDocument, Transition


def export_fountain(doc: ScriptDocument) -> str:
    """Export canonical ScriptDocument AST to standard .fountain plain-text syntax."""
    lines: list[str] = []
    meta = doc.metadata

    lines.append(f"Title: {meta.title}")
    if meta.writers:
        lines.append(f"Author: {', '.join(meta.writers)}")
    lines.append(f"Source: {meta.source}")
    if meta.year:
        lines.append(f"Draft date: {meta.year}")
    lines.append("")

    for scene in doc.scenes:
        heading = scene.heading.strip()
        if not heading.upper().startswith(("INT", "EXT", "I/E", ".")):
            heading = f".{heading}"
        lines.append(heading)
        lines.append("")

        for elem in scene.elements:
            if isinstance(elem, Action):
                lines.append(elem.text)
                lines.append("")
            elif isinstance(elem, Dialogue):
                mods = " ".join(f"({m})" for m in elem.modifiers)
                cue = f"{elem.character} {mods}".strip()
                if elem.dual and not cue.endswith("^"):
                    cue = f"{cue}^"
                lines.append(cue)
                if elem.parenthetical:
                    lines.append(f"({elem.parenthetical})")
                lines.append(elem.lines)
                lines.append("")
            elif isinstance(elem, Transition):
                trans = elem.text.strip()
                if not trans.endswith("TO:") and not trans.startswith(">"):
                    trans = f"> {trans}"
                lines.append(trans)
                lines.append("")

    return "\n".join(lines).strip() + "\n"


def export_txt(doc: ScriptDocument) -> str:
    """Export readable plain text screenplay representation."""
    return export_fountain(doc)
