# Exporters & Analytics Module (`rtfs.exporters`)

[← Back to Documentation Index](README.md)

This guide covers `rtfs.exporters.fountain_exp`, `rtfs.exporters.json_exp`, `rtfs.exporters.fdx_exp`, and `rtfs.exporters.stats_exp`.

## Table of Contents

- [1. Fountain & Plain-Text Exporter (`rtfs.exporters.fountain_exp`)](#1-fountain--plain-text-exporter-rtfsexportersfountain_exp)
- [2. Final Draft `.fdx` XML Exporter (`rtfs.exporters.fdx_exp`)](#2-final-draft-fdx-xml-exporter-rtfsexportersfdx_exp)
- [3. Structured JSON Exporter (`rtfs.exporters.json_exp`)](#3-structured-json-exporter-rtfsexportersjson_exp)
- [4. Script Analytics Exporter (`rtfs.exporters.stats_exp`)](#4-script-analytics-exporter-rtfsexportersstats_exp)

## 1. Fountain & Plain-Text Exporter (`rtfs.exporters.fountain_exp`)

`export_fountain` (and `export_txt`) renders a `ScriptDocument` to standard Fountain syntax, including title-page headers, forced scene headings (`.` prefix for non-`INT./EXT.` headings), forced transitions (`>` prefix when not ending in `TO:`), and `^` dual-dialogue markers for `Dialogue(dual=True)`.

```python
from rtfs.core.models import (
    Action,
    Dialogue,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    Transition,
)
from rtfs.exporters.fountain_exp import export_fountain, export_txt

doc = ScriptDocument(
    metadata=ScriptMetadata(
        title="The Matrix",
        year=1999,
        writers=["Lilly Wachowski", "Lana Wachowski"],
        source="scriptslug",
        url="https://www.scriptslug.com/script/the-matrix-1999",
    ),
    scenes=[
        Scene(
            scene_number=1,
            heading="INT. CONSTRUCT - DAY",
            location="CONSTRUCT",
            time_of_day="DAY",
            elements=[
                Action(text="Two leather armchairs sit in an infinite white void."),
                Dialogue(
                    character="MORPHEUS",
                    modifiers=[],
                    parenthetical="gesturing",
                    lines="This is the Construct.",
                    dual=False,
                ),
                Dialogue(
                    character="NEO",
                    modifiers=["V.O."],
                    parenthetical=None,
                    lines="Is this real?",
                    dual=True,
                ),
                Transition(text="FADE TO BLACK."),
            ],
        )
    ],
)

fountain_output = export_fountain(doc)
print(fountain_output)
assert "MORPHEUS" in fountain_output
assert "NEO (V.O.)^" in fountain_output
assert "> FADE TO BLACK." in fountain_output
assert export_txt(doc) == fountain_output
```

## 2. Final Draft `.fdx` XML Exporter (`rtfs.exporters.fdx_exp`)

`export_fdx` generates Final Draft Version 5 XML (`<FinalDraft DocumentType="Script" Template="No" Version="5">`) with `<TitlePage>` metadata, `<Paragraph>` blocks, `<DualDialogue>` grouping for simultaneous dialogue, and automatic stripping of illegal XML 1.0 control characters.

```python
from rtfs.core.models import RawScript
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.parsers.fdx import FdxParser

# Export ScriptDocument to Final Draft .fdx XML
fdx_xml = export_fdx(doc)
assert fdx_xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
assert "<DualDialogue>" in fdx_xml

# Round-trip back through FdxParser
reparsed = FdxParser().parse(
    RawScript(content=fdx_xml, content_type="fdx", metadata=doc.metadata)
)
assert len(reparsed.scenes) == 1
assert reparsed.scenes[0].heading == "INT. CONSTRUCT - DAY"
```

## 3. Structured JSON Exporter (`rtfs.exporters.json_exp`)

`export_json` serializes the complete `ScriptDocument` AST to formatted JSON with discriminated `type` tags (`"action"`, `"dialogue"`, `"transition"`).

```python
import json
from rtfs.exporters.json_exp import export_json

json_payload = export_json(doc, indent=2)
parsed = json.loads(json_payload)
assert parsed["metadata"]["title"] == "The Matrix"
assert parsed["scenes"][0]["elements"][2]["dual"] is True
```

## 4. Script Analytics Exporter (`rtfs.exporters.stats_exp`)

`compute_stats` calculates scene counts, `INT.` vs. `EXT.` ratios, dialogue-to-action word ratios, and top speaking characters (`ScriptStats` and `CharacterStat`), counting all dialogue turns including simultaneous `dual=True` lines.

```python
from rtfs.exporters.stats_exp import CharacterStat, ScriptStats, compute_stats

stats: ScriptStats = compute_stats(doc, top_n=10)

print(f"Title: {stats.title} ({stats.source})")
print(f"Total Scenes: {stats.total_scenes} (INT={stats.int_scenes}, EXT={stats.ext_scenes})")
print(f"INT/EXT Ratio: {stats.int_ext_ratio}")
print(f"Dialogue/Action Ratio: {stats.dialogue_to_action_ratio}")

for char_stat in stats.top_characters:
    assert isinstance(char_stat, CharacterStat)
    print(
        f"  {char_stat.character}: "
        f"{char_stat.dialogue_turns} turns, {char_stat.word_count} words"
    )
```
