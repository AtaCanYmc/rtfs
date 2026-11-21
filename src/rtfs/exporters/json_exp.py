from __future__ import annotations

from rtfs.core.models import ScriptDocument


def export_json(doc: ScriptDocument, indent: int = 2) -> str:
    """Export canonical ScriptDocument AST to formatted JSON."""
    return doc.model_dump_json(indent=indent)
