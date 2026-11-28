from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rtfs.cli.main import app
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.exporters.breakdown_exp import compute_breakdown
from rtfs.exporters.stats_exp import compute_stats
from rtfs.parsers.base import is_scene_heading, normalize_character_name
from rtfs.parsers.fountain import FountainParser

TR_SCRIPT = """İÇ. KAHVEHANE - GÜNDÜZ

Yağmur cama vuruyor.

ALİ (DIŞ SES)
Buraya gelmemeliydik.

AYŞE (TELEFONDA)
Hemen çıkıyorum.

DIŞ. SOKAK - GECE

ALİ
Bekliyorum.
"""


def test_turkish_scene_headings_and_character_normalization() -> None:
    assert is_scene_heading("İÇ. KAHVEHANE - GÜNDÜZ") is True
    assert is_scene_heading("DIŞ. SOKAK - GECE") is True
    assert is_scene_heading("İÇ/DIŞ. ARABA - GECE") is True
    assert normalize_character_name("ALİ (DIŞ SES)") == "ALİ"
    assert normalize_character_name("AYŞE (TELEFONDA)") == "AYŞE"

    raw = RawScript(
        content=TR_SCRIPT,
        content_type="fountain",
        metadata=ScriptMetadata(title="Yerli Yapım", source="local", url="file://tr.fountain"),
    )
    doc = FountainParser().parse(raw)
    assert len(doc.scenes) == 2

    stats = compute_stats(doc)
    assert stats.int_scenes == 1
    assert stats.ext_scenes == 1
    names = {c.character for c in stats.top_characters}
    assert names == {"ALİ", "AYŞE"}


def test_compute_breakdown_and_cli_command(tmp_path: Path) -> None:
    f = tmp_path / "tr.fountain"
    f.write_text(TR_SCRIPT, encoding="utf-8")

    raw = RawScript(
        content=TR_SCRIPT,
        content_type="fountain",
        metadata=ScriptMetadata(title="Yerli Yapım", source="local", url="file://tr.fountain"),
    )
    doc = FountainParser().parse(raw)
    bd = compute_breakdown(doc)
    assert bd.total_scenes == 2
    assert bd.total_estimated_minutes >= 0.5
    assert bd.characters == ["ALİ", "AYŞE"]
    assert bd.scenes[0].int_ext == "INT"
    assert bd.scenes[1].int_ext == "EXT"

    runner = CliRunner()
    result = runner.invoke(app, ["breakdown", str(f)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total_scenes"] == 2
