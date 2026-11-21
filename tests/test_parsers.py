from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest
from pydantic import ValidationError

from rtfs.core.models import Action, Dialogue, RawScript, ScriptMetadata, Transition
from rtfs.parsers.base import (
    cluster_x_positions,
    is_character_candidate,
    is_noise_line,
    is_transition,
    parse_character_cue,
    parse_heading,
)
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
    assert d.dual is False

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


@pytest.mark.parametrize(
    ("raw_heading", "expected_loc", "expected_tod"),
    [
        ("INT. SERVER ROOM - NIGHT", "SERVER ROOM", "NIGHT"),
        ("42A EXT. HIGHWAY OVERPASS -- CONTINUOUS", "HIGHWAY OVERPASS", "CONTINUOUS"),
        ("I/E. PATROL CAR - MOVING", "PATROL CAR", "MOVING"),
        ("EXT. DESERT", "DESERT", None),
        ("NON_STANDARD_HEADING", None, None),
    ],
)
def test_parse_heading_variants(
    raw_heading: str,
    expected_loc: str | None,
    expected_tod: str | None,
) -> None:
    _, loc, tod = parse_heading(raw_heading)
    assert loc == expected_loc
    assert tod == expected_tod


@pytest.mark.parametrize(
    ("cue", "expected_name", "expected_mods"),
    [
        ("MORPHEUS (V.O.) (CONT'D)", "MORPHEUS", ["V.O.", "CONT'D"]),
        ("DR. KING SCHULTZ (O.S.)", "DR. KING SCHULTZ", ["O.S."]),
        ("MR. ANDERSON:", "MR. ANDERSON", []),
    ],
)
def test_parse_character_cue_and_candidates(
    cue: str,
    expected_name: str,
    expected_mods: list[str],
) -> None:
    assert is_character_candidate(cue) is True
    name, mods = parse_character_cue(cue)
    assert name == expected_name
    assert mods == expected_mods


@pytest.mark.parametrize(
    "non_char",
    [
        "A sentence ending with a period.",
        "(whispering)",
        "CUT TO:",
        "INT. ROOM - DAY",
        "CONTINUED:",
        "12A.",
    ],
)
def test_is_character_candidate_rejects_non_characters(non_char: str) -> None:
    assert is_character_candidate(non_char) is False


@pytest.mark.parametrize(
    "noise",
    [
        "",
        "   ",
        "CONTINUED:",
        "(CONTINUED)",
        "CONTINUED: (2)",
        "(MORE)",
        "42.",
        "14A.",
        "BLUE REV. 04/15/21",
    ],
)
def test_is_noise_line_filters_page_artifacts(noise: str) -> None:
    assert is_noise_line(noise) is True


@pytest.mark.parametrize(
    "transition",
    [
        "CUT TO:",
        "FADE IN:",
        "FADE OUT.",
        "SMASH CUT TO:",
        "DISSOLVE TO:",
        "FLASHBACK TO:",
    ],
)
def test_is_transition_recognizes_standard_transitions(transition: str) -> None:
    assert is_transition(transition) is True


def test_cluster_x_positions_groups_within_tolerance() -> None:
    assert cluster_x_positions([]) == []
    pts = [72.0, 73.5, 71.0, 144.0, 145.0, 216.0]
    clusters = cluster_x_positions(pts, tolerance=8.0)
    assert len(clusters) == 3
    assert abs(clusters[0] - 72.16) < 1.0
    assert abs(clusters[1] - 144.5) < 1.0
    assert abs(clusters[2] - 216.0) < 1.0


def test_html_parser_empty_content_returns_empty_scenes() -> None:
    raw = RawScript(
        content="<pre>   \n  CONTINUED: \n 12. </pre>",
        content_type="html",
        metadata=_make_metadata(),
    )
    doc = HtmlScreenplayParser().parse(raw)
    assert doc.scenes == []


def test_dialogue_dual_strict_bool_and_raw_content_type_fdx() -> None:
    d = Dialogue(character="NEO", lines="Whoa.", dual=True)
    assert d.dual is True

    with pytest.raises(ValidationError):
        Dialogue(character="NEO", lines="Whoa.", dual=1)  # type: ignore[arg-type]

    raw = RawScript(
        content="<FinalDraft/>",
        content_type="fdx",
        metadata=_make_metadata(),
    )
    assert raw.content_type == "fdx"


def test_pdf_dual_column_simultaneous_dialogue() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text((72, 90), "INT. COMMAND CENTER - NIGHT")
    page.insert_text((72, 115), "Alarms blare across the bridge.")

    # Single-column dialogue before dual dialogue
    page.insert_text((216, 145), "CAPTAIN")
    page.insert_text((144, 159), "Status report now!")

    # Dual-column simultaneous dialogue (asymmetric heights + slight y0 offset)
    page.insert_text((120, 190), "ALICE (V.O.)")
    page.insert_text((100, 204), "(urgent)")
    page.insert_text((72, 218), "Shut down the")
    page.insert_text((72, 230), "main reactor")
    page.insert_text((72, 242), "right now!")

    page.insert_text((380, 192), "BOB (O.S.)")
    page.insert_text((360, 206), "(calmly)")
    page.insert_text((340, 220), "Already on it.")

    # Surrounding single-column action and dialogue after dual block
    page.insert_text((72, 278), "The console lights flicker.")
    page.insert_text((216, 308), "CAPTAIN")
    page.insert_text((144, 322), "Good work.")

    pdf_bytes = doc.tobytes()
    doc.close()

    raw = RawScript(content=pdf_bytes, content_type="pdf", metadata=_make_metadata())
    parsed = PdfScreenplayParser().parse(raw)

    assert len(parsed.scenes) == 1
    elements = parsed.scenes[0].elements
    assert isinstance(elements[0], Action)
    assert "Alarms blare" in elements[0].text

    dialogues = [e for e in elements if isinstance(e, Dialogue)]
    assert len(dialogues) == 4

    assert dialogues[0].character == "CAPTAIN"
    assert dialogues[0].dual is False

    assert dialogues[1].character == "ALICE"
    assert dialogues[1].modifiers == ["V.O."]
    assert dialogues[1].parenthetical == "urgent"
    assert dialogues[1].lines == "Shut down the main reactor right now!"
    assert dialogues[1].dual is False

    assert dialogues[2].character == "BOB"
    assert dialogues[2].modifiers == ["O.S."]
    assert dialogues[2].parenthetical == "calmly"
    assert dialogues[2].lines == "Already on it."
    assert dialogues[2].dual is True

    assert dialogues[3].character == "CAPTAIN"
    assert dialogues[3].lines == "Good work."
    assert dialogues[3].dual is False

    actions = [e for e in elements if isinstance(e, Action)]
    assert len(actions) == 2
    assert "console lights flicker" in actions[1].text


def test_pdf_dual_column_asymmetric_parenthetical() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text((72, 90), "INT. LAB - DAY")
    page.insert_text((120, 130), "ALICE")
    page.insert_text((100, 144), "(whispering)")
    page.insert_text((72, 158), "Stay quiet.")

    page.insert_text((380, 130), "BOB")
    page.insert_text((340, 158), "Right behind you.")

    pdf_bytes = doc.tobytes()
    doc.close()

    raw = RawScript(content=pdf_bytes, content_type="pdf", metadata=_make_metadata())
    parsed = PdfScreenplayParser().parse(raw)

    dialogues = [e for e in parsed.scenes[0].elements if isinstance(e, Dialogue)]
    assert len(dialogues) == 2
    assert dialogues[0].character == "ALICE"
    assert dialogues[0].parenthetical == "whispering"
    assert dialogues[0].lines == "Stay quiet."
    assert dialogues[0].dual is False
    assert dialogues[1].character == "BOB"
    assert dialogues[1].parenthetical is None
    assert dialogues[1].lines == "Right behind you."
    assert dialogues[1].dual is True


def test_pdf_dual_column_span_splitting(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = PdfScreenplayParser()

    # Direct unit test of _split_line_spans on wide-gap spans with whitespace span
    split_result = parser._split_line_spans(
        {
            "bbox": (120.0, 140.0, 440.0, 155.0),
            "spans": [
                {"bbox": (120.0, 140.0, 165.0, 155.0), "text": "ALICE", "size": 12.0},
                {"bbox": (165.0, 140.0, 380.0, 155.0), "text": "   ", "size": 12.0},
                {"bbox": (380.0, 140.0, 440.0, 155.0), "text": "BOB", "size": 12.0},
            ],
        }
    )
    assert len(split_result) == 2
    assert split_result[0] == ((120.0, 140.0, 165.0, 155.0), "ALICE")
    assert split_result[1] == ((380.0, 140.0, 440.0, 155.0), "BOB")

    # End-to-end parse via synthetic PyMuPDF dict where PyMuPDF kept both columns on one line
    fake_page_dict: dict[str, Any] = {
        "blocks": [
            {
                "type": 0,
                "lines": [
                    {
                        "bbox": (72.0, 90.0, 260.0, 105.0),
                        "spans": [
                            {
                                "bbox": (72.0, 90.0, 260.0, 105.0),
                                "text": "INT. STUDIO - NIGHT",
                                "size": 12.0,
                            }
                        ],
                    },
                    {
                        "bbox": (120.0, 130.0, 430.0, 145.0),
                        "spans": [
                            {"bbox": (120.0, 130.0, 165.0, 145.0), "text": "ALICE", "size": 12.0},
                            {"bbox": (165.0, 130.0, 380.0, 145.0), "text": "   ", "size": 12.0},
                            {"bbox": (380.0, 130.0, 430.0, 145.0), "text": "BOB", "size": 12.0},
                        ],
                    },
                    {
                        "bbox": (72.0, 144.0, 460.0, 159.0),
                        "spans": [
                            {
                                "bbox": (72.0, 144.0, 175.0, 159.0),
                                "text": "We start now.",
                                "size": 12.0,
                            },
                            {"bbox": (175.0, 144.0, 340.0, 159.0), "text": "   ", "size": 12.0},
                            {
                                "bbox": (340.0, 144.0, 460.0, 159.0),
                                "text": "Count me in.",
                                "size": 12.0,
                            },
                        ],
                    },
                ],
            }
        ]
    }

    class _FakePage:
        def get_text(self, mode: str) -> dict[str, Any]:
            assert mode == "dict"
            return fake_page_dict

    class _FakeDoc:
        def __iter__(self) -> Any:
            return iter([_FakePage()])

        def close(self) -> None:
            return None

    monkeypatch.setattr(fitz, "open", lambda **_: _FakeDoc())

    raw = RawScript(content=b"%PDF-1.4", content_type="pdf", metadata=_make_metadata())
    parsed = parser.parse(raw)
    dialogues = [e for e in parsed.scenes[0].elements if isinstance(e, Dialogue)]
    assert len(dialogues) == 2
    assert dialogues[0].character == "ALICE"
    assert dialogues[0].lines == "We start now."
    assert dialogues[0].dual is False
    assert dialogues[1].character == "BOB"
    assert dialogues[1].lines == "Count me in."
    assert dialogues[1].dual is True


def test_pdf_single_column_non_regression_with_all_caps_dialogue() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text((72, 90), "INT. BUNKER - NIGHT")
    page.insert_text((72, 115), "Steel doors slam shut.")
    page.insert_text((72, 127), "Dust falls from the ceiling.")

    page.insert_text((216, 158), "NEO")
    page.insert_text((180, 172), "(shouting)")
    page.insert_text((144, 186), "NO!")
    page.insert_text((144, 198), "Get back inside!")

    pdf_bytes = doc.tobytes()
    doc.close()

    raw = RawScript(content=pdf_bytes, content_type="pdf", metadata=_make_metadata())
    parsed = PdfScreenplayParser().parse(raw)

    assert len(parsed.scenes) == 1
    dialogues = [e for e in parsed.scenes[0].elements if isinstance(e, Dialogue)]
    assert len(dialogues) == 1
    assert dialogues[0].character == "NEO"
    assert dialogues[0].parenthetical == "shouting"
    assert dialogues[0].lines == "NO! Get back inside!"
    assert dialogues[0].dual is False


