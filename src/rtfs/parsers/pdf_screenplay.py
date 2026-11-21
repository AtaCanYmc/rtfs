from __future__ import annotations

from dataclasses import dataclass

import pymupdf as fitz

from rtfs.core.models import RawScript, ScriptDocument
from rtfs.parsers.base import (
    BaseParser,
    build_scenes_from_tagged_blocks,
    cluster_x_positions,
    is_character_candidate,
    is_noise_line,
    is_scene_heading,
    is_transition,
)


@dataclass
class PdfLine:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 8.0)


class PdfScreenplayParser(BaseParser):
    """Coordinate-clustering PDF screenplay parser using PyMuPDF."""

    def __init__(
        self,
        header_cutoff: float = 50.0,
        footer_cutoff: float = 740.0,
        cluster_tolerance: float = 8.0,
        max_pages: int = 500,
    ) -> None:
        self.header_cutoff = header_cutoff
        self.footer_cutoff = footer_cutoff
        self.cluster_tolerance = cluster_tolerance
        self.max_pages = max_pages

    def _extract_lines(self, pdf_bytes: bytes) -> list[PdfLine]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        extracted: list[PdfLine] = []
        try:
            for page_idx, page in enumerate(doc):
                if page_idx >= self.max_pages:
                    break
                page_dict = page.get_text("dict")
                page_lines: list[PdfLine] = []
                for block in page_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        bbox = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
                        x0, y0, x1, y1 = (
                            float(bbox[0]),
                            float(bbox[1]),
                            float(bbox[2]),
                            float(bbox[3]),
                        )
                        if y0 < self.header_cutoff or y1 > self.footer_cutoff:
                            continue
                        spans = line.get("spans", [])
                        text = "".join(span.get("text", "") for span in spans).strip()
                        if not text or is_noise_line(text):
                            continue
                        page_lines.append(PdfLine(page_idx, x0, y0, x1, y1, text))

                page_lines.sort(key=lambda ln: (round(ln.y0, 1), ln.x0))
                extracted.extend(page_lines)
        finally:
            doc.close()
        return extracted

    def _classify_line(
        self,
        line: PdfLine,
        action_margin: float,
        dialogue_margin: float,
        char_margin: float,
        in_dialogue: bool,
    ) -> str:
        text = line.text.strip()
        x0 = line.x0

        if is_scene_heading(text):
            return "heading"

        if is_transition(text) or (x0 > char_margin + 60 and text.isupper()):
            return "transition"

        if text.startswith("(") and text.endswith(")") and x0 >= action_margin + 15:
            return "parenthetical"

        if is_character_candidate(text) and x0 >= dialogue_margin + 15:
            return "character"

        if abs(x0 - action_margin) <= self.cluster_tolerance * 1.5:
            return "action"

        if in_dialogue and x0 >= action_margin + 15:
            return "dialogue"

        if abs(x0 - dialogue_margin) <= self.cluster_tolerance * 2.0:
            return "dialogue" if in_dialogue else "action"

        return "dialogue" if in_dialogue else "action"

    def parse(self, raw: RawScript) -> ScriptDocument:
        pdf_bytes = (
            raw.content
            if isinstance(raw.content, bytes)
            else raw.content.encode("latin-1")
        )
        lines = self._extract_lines(pdf_bytes)
        if not lines:
            return ScriptDocument(metadata=raw.metadata, scenes=[])

        clusters = cluster_x_positions([ln.x0 for ln in lines], self.cluster_tolerance)
        action_margin = clusters[0]
        dialogue_margin = clusters[1] if len(clusters) > 1 else action_margin + 36.0
        char_margin = (
            clusters[2]
            if len(clusters) > 2
            else (clusters[1] if len(clusters) > 1 else action_margin + 100.0)
        )

        # Ensure sensible margin hierarchy when a short snippet has fewer distinct columns
        char_candidates = [ln.x0 for ln in lines if is_character_candidate(ln.text)]
        if char_candidates:
            char_margin = sum(char_candidates) / len(char_candidates)
        non_action_non_char = [
            ln.x0
            for ln in lines
            if ln.x0 > action_margin + self.cluster_tolerance
            and not is_character_candidate(ln.text)
            and not (ln.text.startswith("(") and ln.text.endswith(")"))
            and not is_transition(ln.text)
        ]
        if non_action_non_char:
            dialogue_margin = min(non_action_non_char)

        merged_blocks: list[tuple[str, str]] = []
        in_dialogue = False
        prev_line: PdfLine | None = None
        prev_kind: str | None = None

        for line in lines:
            kind = self._classify_line(
                line, action_margin, dialogue_margin, char_margin, in_dialogue
            )
            if kind == "character":
                in_dialogue = True
            elif kind in {"heading", "action", "transition"}:
                in_dialogue = False

            if (
                prev_line is not None
                and prev_kind == kind
                and kind in {"action", "dialogue", "parenthetical"}
                and prev_line.page == line.page
                and abs(prev_line.x0 - line.x0) <= self.cluster_tolerance
                and (line.y0 - prev_line.y1) < 1.5 * prev_line.height
            ):
                last_kind, last_text = merged_blocks[-1]
                merged_blocks[-1] = (last_kind, f"{last_text} {line.text}")
            else:
                merged_blocks.append((kind, line.text))

            prev_line = line
            prev_kind = kind

        scenes = build_scenes_from_tagged_blocks(merged_blocks)
        return ScriptDocument(metadata=raw.metadata, scenes=scenes)
