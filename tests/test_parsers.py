from __future__ import annotations

from pathlib import Path

import fitz

from rtfs.core.models import Action, Dialogue, RawScript, ScriptMetadata, Transition
from rtfs.parsers.html_screenplay import HtmlScreenplayParser
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser
from rtfs.parsers.transcript import TranscriptParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_metadata(fmt: str = "screenplay") -> ScriptMetadata:
    return ScriptMetadata(
        title="The Matrix",
        year=1999,
        media_type="movie",
        writers=["Lilly Wachowski", "Lana Wachowski"],
        source="test",
        format=fmt,  # type: ignore[arg-type]
        url="https://example.com/matrix",
    )


def _build_synthetic_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Header noise (y < 50)
    page.insert_text((480, 35), "REV. 03/12/98   2.")
    page.insert_text((72, 65), "CONTINUED:")

    # Scene 1
    page.insert_text((72, 90), "INT. NEBUCHADNEZZAR DECK - NIGHT")
    page.insert_text((72, 115), "Monitors glow in the dim cabin.")
    page.insert_text((72, 127), "Cables snake across the steel floor.")

    # Dialogue 1
    page.insert_text((216, 160), "TRINITY (V.O.)")
    page.insert_text((180, 174), "(whispering)")
    page.insert_text((144, 188), "Everything Morpheus told you")
    page.insert_text((144, 200), "is about to happen.")

    # Transition
    page.insert_text((430, 235), "CUT TO:")

    # Scene 2
    page.insert_text((72, 270), "EXT. CITY ALLEY - DAY")
    page.insert_text((72, 295), "A black phone rings inside a booth.")

    # Footer noise (y > 740)
    page.insert_text((72, 760), "(CONTINUED)")

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_pdf_screenplay_parser() -> None:
    pdf_bytes = _build_synthetic_pdf()
    raw = RawScript(content=pdf_bytes, content_type="pdf", metadata=_make_metadata())

    parser = PdfScreenplayParser()
    doc = parser.parse(raw)

    assert len(doc.scenes) == 2

    scene1 = doc.scenes[0]
    assert scene1.scene_number == 1
    assert scene1.heading == "INT. NEBUCHADNEZZAR DECK - NIGHT"
    assert scene1.location == "NEBUCHADNEZZAR DECK"
    assert scene1.time_of_day == "NIGHT"

    actions = [e for e in scene1.elements if isinstance(e, Action)]
    dialogues = [e for e in scene1.elements if isinstance(e, Dialogue)]
    transitions = [e for e in scene1.elements if isinstance(e, Transition)]

    assert len(actions) == 1
    assert "Monitors glow in the dim cabin. Cables snake across the steel floor." in actions[0].text

    assert len(dialogues) == 1
    d = dialogues[0]
    assert d.character == "TRINITY"
    assert d.modifiers == ["V.O."]
    assert d.parenthetical == "whispering"
    assert d.lines == "Everything Morpheus told you is about to happen."

    assert len(transitions) == 1
    assert transitions[0].text == "CUT TO:"

    scene2 = doc.scenes[1]
    assert scene2.scene_number == 2
    assert scene2.location == "CITY ALLEY"
    assert scene2.time_of_day == "DAY"


def test_html_screenplay_parser_bold_and_whitespace() -> None:
    sample_html = (FIXTURES_DIR / "sample_imsdb.html").read_text(encoding="utf-8")
    raw = RawScript(content=sample_html, content_type="html", metadata=_make_metadata())

    parser = HtmlScreenplayParser()
    doc = parser.parse(raw)

    assert len(doc.scenes) == 2
    s1 = doc.scenes[0]
    assert s1.location == "CONSTRUCT"
    assert s1.time_of_day == "DAY"

    dialogues = [e for e in s1.elements if isinstance(e, Dialogue)]
    assert len(dialogues) == 3

    assert dialogues[0].character == "MORPHEUS"
    assert "loading program" in dialogues[0].lines

    assert dialogues[1].character == "NEO"
    assert dialogues[1].modifiers == ["V.O."]
    assert dialogues[1].parenthetical == "looking around"
    assert dialogues[1].lines == "Is this real?"

    assert dialogues[2].character == "MORPHEUS"
    assert dialogues[2].modifiers == ["CONT'D"]


def test_html_screenplay_parser_pure_whitespace() -> None:
    pure_ws_html = """
    <pre>
    INT. COFFEE SHOP - MORNING

    Steam rises from two ceramic mugs.

                        WALTER
              We need a new distribution channel.

                        JESSE (O.S.)
                  (sighs)
              Yeah, science!
    </pre>
    """
    raw = RawScript(content=pure_ws_html, content_type="html", metadata=_make_metadata())
    doc = HtmlScreenplayParser().parse(raw)

    assert len(doc.scenes) == 1
    dialogues = [e for e in doc.scenes[0].elements if isinstance(e, Dialogue)]
    assert len(dialogues) == 2
    assert dialogues[0].character == "WALTER"
    assert dialogues[1].character == "JESSE"
    assert dialogues[1].modifiers == ["O.S."]
    assert dialogues[1].parenthetical == "sighs"


def test_transcript_parser() -> None:
    transcript_html = """
    <html><body><div class="full-script">
    INT. INTERROGATION ROOM - NIGHT<br>
    [Door slams shut]<br>
    AGENT SMITH: (calmly) Mr. Anderson.<br>
    NEO: You can't scare me.<br>
    Unattributed subtitle line here.<br>
    </div></body></html>
    """
    raw = RawScript(
        content=transcript_html,
        content_type="text",
        metadata=_make_metadata(fmt="transcript"),
    )
    doc = TranscriptParser().parse(raw)

    assert len(doc.scenes) == 1
    s = doc.scenes[0]
    assert s.location == "INTERROGATION ROOM"
    assert isinstance(s.elements[0], Action)
    assert s.elements[0].text == "Door slams shut"

    assert isinstance(s.elements[1], Dialogue)
    assert s.elements[1].character == "AGENT SMITH"
    assert s.elements[1].parenthetical == "calmly"
    assert s.elements[1].lines == "Mr. Anderson."

    assert isinstance(s.elements[2], Dialogue)
    assert s.elements[2].character == "NEO"
    assert s.elements[2].lines == "You can't scare me."
