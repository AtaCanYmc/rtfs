from __future__ import annotations

import builtins
import subprocess
import sys


def test_pure_python_parsers_and_exporters_import_without_optional_deps() -> None:
    """Verify pure-Python modules import and run without fitz, httpx, typer, or extras."""
    code = """
import builtins, sys

BLOCKED = {
    "pymupdf", "fitz", "httpx", "typer", "rich", "mcp",
    "redis", "fastapi", "pytesseract", "fastembed", "textual",
    "diskcache",
}
real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    top = name.split(".")[0]
    if top in BLOCKED:
        raise ImportError(f"Blocked in Pyodide test: {name}")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import

from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.core.diff import diff_documents
from rtfs.parsers.fountain import FountainParser
from rtfs.parsers.fdx import FdxParser
from rtfs.parsers.transcript import TranscriptParser
from rtfs.exporters.fountain_exp import export_fountain
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.exporters.json_exp import export_json
from rtfs.exporters.stats_exp import compute_stats, export_stats_mermaid

meta = ScriptMetadata(title="Pyodide", source="local", url="file://test.fountain")
raw = RawScript(
    content="INT. LAB - NIGHT\\n\\nALICE\\nHello.\\n\\nBOB ^\\nHi.\\n",
    content_type="fountain",
    metadata=meta,
)
doc = FountainParser().parse(raw)
assert len(doc.scenes) == 1
assert "<FinalDraft" in export_fdx(doc)
assert "INT. LAB - NIGHT" in export_fountain(doc)
assert '"title": "Pyodide"' in export_json(doc)
stats = compute_stats(doc)
assert stats.total_scenes == 1
assert "flowchart LR" in export_stats_mermaid(stats)
assert diff_documents(doc, doc) == ""
print("PYODIDE_SAFE_OK")
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"STDERR:\n{res.stderr}"
    assert "PYODIDE_SAFE_OK" in res.stdout
    _ = builtins


def test_rtfs_lazy_getattr_and_unknown_attribute() -> None:
    import pytest

    import rtfs

    assert rtfs.ScriptDocument.__name__ == "ScriptDocument"
    assert rtfs.export_json.__name__ == "export_json"
    with pytest.raises(AttributeError, match="no_such_attr"):
        _ = rtfs.no_such_attr
