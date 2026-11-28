# Parsers Module (`rtfs.parsers`)

[← Back to Documentation Index](README.md)

This guide covers `rtfs.parsers.base`, `rtfs.parsers.pdf_screenplay`, `rtfs.parsers.html_screenplay`, `rtfs.parsers.transcript`, and `rtfs.parsers.fdx`.

## Table of Contents

- [1. PDF Screenplay Parser & Dual-Column Dialogue (`rtfs.parsers.pdf_screenplay`)](#1-pdf-screenplay-parser--dual-column-dialogue-rtfsparserspdf_screenplay)
- [2. Final Draft `.fdx` XML Parser (`rtfs.parsers.fdx`)](#2-final-draft-fdx-xml-parser-rtfsparsersfdx)
- [3. HTML Screenplay Parser (`rtfs.parsers.html_screenplay`)](#3-html-screenplay-parser-rtfsparsershtml_screenplay)
- [4. Plain-Text & HTML Transcript Parser (`rtfs.parsers.transcript`)](#4-plain-text--html-transcript-parser-rtfsucceedingtranscript)
- [5. Shared Parsing Utilities (`rtfs.parsers.base`)](#5-shared-parsing-utilities-rtfsparsersbase)

## 1. PDF Screenplay Parser & Dual-Column Dialogue (`rtfs.parsers.pdf_screenplay`)

`PdfScreenplayParser` extracts text lines with bounding boxes `(x0, y0, x1, y1)` using PyMuPDF, strips headers (`y0 < 50`), footers (`y1 > 740`), page numbers, revision markers, and `(CONTINUED)` tags, clusters horizontal `x0` margins, and detects side-by-side simultaneous dialogue columns via vertical `y0`/`y1` intersection across separate `x0` regions.

```python
import pymupdf as fitz
from rtfs.core.models import Dialogue, RawScript, ScriptMetadata
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser

# 1. Build a synthetic PDF containing both single-column and dual-column simultaneous dialogue
pdf_doc = fitz.open()
page = pdf_doc.new_page(width=612, height=792)

# Scene heading & action at left margin (x0 = 72)
page.insert_text((72, 90), "INT. COMMAND BRIDGE - NIGHT")
page.insert_text((72, 115), "Red warning lights pulse across the main console.")

# Standard single-column dialogue (character x0 = 216, lines x0 = 144)
page.insert_text((216, 150), "MORPHEUS (V.O.)")
page.insert_text((180, 164), "(calmly)")
page.insert_text((144, 178), "Wait for my signal.")

# Dual-column simultaneous dialogue at overlapping y-coordinates (y = 220..250)
# Left column (x0 ~ 108..144)
page.insert_text((144, 220), "TRINITY")
page.insert_text((108, 235), "Watch the left corridor!")

# Right column (x0 ~ 342..378)
page.insert_text((378, 220), "NEO")
page.insert_text((342, 235), "I see movement ahead!")

pdf_bytes = pdf_doc.tobytes()
pdf_doc.close()

# 2. Parse into ScriptDocument
raw = RawScript(
    content=pdf_bytes,
    content_type="pdf",
    metadata=ScriptMetadata(
        title="Bridge Test",
        source="local",
        url="file:///bridge.pdf",
    ),
)

parser = PdfScreenplayParser(
    header_cutoff=50.0,
    footer_cutoff=740.0,
    cluster_tolerance=8.0,
    max_pages=500,
)
script_doc = parser.parse(raw)

scene = script_doc.scenes[0]
dialogues = [el for el in scene.elements if isinstance(el, Dialogue)]
assert len(dialogues) == 3

assert dialogues[0].character == "MORPHEUS"
assert dialogues[0].dual is False

# Left speaker in simultaneous pair has dual=False, right speaker has dual=True
assert dialogues[1].character == "TRINITY"
assert dialogues[1].dual is False
assert dialogues[2].character == "NEO"
assert dialogues[2].dual is True
```

## 2. Final Draft `.fdx` XML Parser (`rtfs.parsers.fdx`)

`FdxParser` uses Python's `xml.parsers.expat` with all DTD and entity handlers disabled (`StartDoctypeDeclHandler`, `EntityDeclHandler`, `ExternalEntityRefHandler`), blocking XXE and Billion Laughs attacks while extracting title-page credits, scene headings, action paragraphs, dialogue, and `<DualDialogue>` blocks.

```python
from rtfs.core.models import Dialogue, RawScript, ScriptMetadata
from rtfs.parsers.fdx import FdxParser

fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
  <TitlePage>
    <Content>
      <Paragraph Type="Title"><Text>The Construct</Text></Paragraph>
      <Paragraph Type="Writer"><Text>Lilly Wachowski</Text></Paragraph>
      <Paragraph Type="Writer"><Text>Lana Wachowski</Text></Paragraph>
    </Content>
  </TitlePage>
  <Content>
    <Paragraph Type="Scene Heading">
      <Text>INT. DOJO - DAY</Text>
    </Paragraph>
    <Paragraph Type="Action">
      <Text>Two figures circle each other on tatami mats.</Text>
    </Paragraph>
    <Paragraph>
      <DualDialogue>
        <Paragraph Type="Character"><Text>MORPHEUS</Text></Paragraph>
        <Paragraph Type="Dialogue"><Text>Stop trying to hit me and hit me!</Text></Paragraph>
        <Paragraph Type="Character"><Text>NEO (O.S.)</Text></Paragraph>
        <Paragraph Type="Parenthetical"><Text>(breathing hard)</Text></Paragraph>
        <Paragraph Type="Dialogue"><Text>I know Kung Fu.</Text></Paragraph>
      </DualDialogue>
    </Paragraph>
  </Content>
</FinalDraft>
"""

raw = RawScript(
    content=fdx_xml,
    content_type="fdx",
    metadata=ScriptMetadata(
        title="",
        source="local",
        url="file:///construct.fdx",
    ),
)

doc = FdxParser().parse(raw)
assert doc.metadata.title == "The Construct"
assert doc.metadata.writers == ["Lilly Wachowski", "Lana Wachowski"]

dialogues = [el for el in doc.scenes[0].elements if isinstance(el, Dialogue)]
assert dialogues[0].character == "MORPHEUS"
assert dialogues[0].dual is False
assert dialogues[1].character == "NEO"
assert dialogues[1].modifiers == ["O.S."]
assert dialogues[1].parenthetical == "breathing hard"
assert dialogues[1].dual is True
```

## 3. HTML Screenplay Parser (`rtfs.parsers.html_screenplay`)

`HtmlScreenplayParser` parses both `<b>`-tagged HTML scripts (standard IMSDb format) and pure whitespace-indented `<pre>` blocks.

```python
from rtfs.core.models import Dialogue, RawScript, ScriptMetadata
from rtfs.parsers.html_screenplay import HtmlScreenplayParser

html_payload = """
<html><body><table><tr><td class="scrtext">
<pre>
<b>INT. INTERROGATION ROOM - DAY</b>

Cold fluorescent light buzzes overhead.

                    <b>AGENT SMITH</b>
              (leaning forward)
          Tell me, Mr. Anderson... what good is a phone
          call if you are unable to speak?
</pre>
</td></tr></table></body></html>
"""

raw = RawScript(
    content=html_payload,
    content_type="html",
    metadata=ScriptMetadata(
        title="The Matrix",
        source="imsdb",
        url="https://imsdb.com/scripts/Matrix,-The.html",
    ),
)

doc = HtmlScreenplayParser().parse(raw)
assert doc.scenes[0].location == "INTERROGATION ROOM"
dlg = next(el for el in doc.scenes[0].elements if isinstance(el, Dialogue))
assert dlg.character == "AGENT SMITH"
assert dlg.parenthetical == "leaning forward"
```

## 4. Plain-Text & HTML Transcript Parser (`rtfs.parsers.transcript`)

`TranscriptParser` converts `SPEAKER: line` dialogue, `[stage directions]`, and raw subtitle lines from plain text or SubsLikeScript `<div class="full-script">` pages into a `ScriptDocument`.

```python
from rtfs.core.models import Action, Dialogue, RawScript, ScriptMetadata
from rtfs.parsers.transcript import TranscriptParser

transcript_text = """
INT. CONTROL ROOM - NIGHT
[Alarms blare in the distance]
LEGASOV (V.O.): (quietly) What is the cost of lies?
SHCHERBINA: Explain to me how an RBMK reactor core explodes.
Unattributed subtitle line.
"""

raw = RawScript(
    content=transcript_text,
    content_type="text",
    metadata=ScriptMetadata(
        title="Chernobyl",
        media_type="tv",
        source="subslikescript",
        format="transcript",
        url="https://subslikescript.com/series/Chernobyl-7366338",
    ),
)

doc = TranscriptParser().parse(raw)
elements = doc.scenes[0].elements
assert isinstance(elements[0], Action)
assert elements[0].text == "Alarms blare in the distance"
assert isinstance(elements[1], Dialogue)
assert elements[1].character == "LEGASOV"
assert elements[1].modifiers == ["V.O."]
assert elements[1].parenthetical == "quietly"
```

## 5. Shared Parsing Utilities (`rtfs.parsers.base`)

`rtfs.parsers.base` contains low-level classifiers and clustering functions reused across parsers:

```python
from rtfs.parsers.base import (
    cluster_x_positions,
    is_character_candidate,
    is_noise_line,
    is_scene_heading,
    is_transition,
    parse_character_cue,
    parse_heading,
)

# Scene heading decomposition
heading, location, time_of_day = parse_heading("14A INT. SERVER VAULT - CONTINUOUS")
assert location == "SERVER VAULT"
assert time_of_day == "CONTINUOUS"
assert is_scene_heading("EXT. DESERT HIGHWAY - DAWN") is True

# Character cue extraction
name, modifiers = parse_character_cue("DR. KING SCHULTZ (O.S.) (CONT'D)")
assert name == "DR. KING SCHULTZ"
assert modifiers == ["O.S.", "CONT'D"]
assert is_character_candidate("DR. KING SCHULTZ (O.S.)") is True

# Transitions and page noise
assert is_transition("SMASH CUT TO:") is True
assert is_noise_line("CONTINUED: (2)") is True
assert is_noise_line("BLUE REV. 03/12/99") is True

# 1D left-margin coordinate clustering
centers = cluster_x_positions([72.0, 73.0, 144.0, 145.5, 216.0], tolerance=8.0)
assert len(centers) == 3
```

## Local Tesseract OCR (`pyrtfs[ocr]`)

Install the optional OCR extra to parse image-only scanned PDFs with zero custom glue code:

```bash
pip install "pyrtfs[ocr]"
rtfs parse ./scanned_script.pdf --ocr --format fountain
```
