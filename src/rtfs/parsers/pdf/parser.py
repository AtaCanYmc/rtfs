from __future__ import annotations

from typing import Any

from rtfs.core.models import Dialogue, RawScript, SceneElement, ScriptDocument
from rtfs.parsers.base import (
    BaseParser,
    build_scenes_from_tagged_blocks,
    cluster_x_positions,
    is_character_candidate,
    is_scene_heading,
    is_transition,
    parse_character_cue,
)
from rtfs.parsers.pdf.dual_column import (
    find_dual_bands,
    lines_are_dual_pair,
    parse_dual_column,
)
from rtfs.parsers.pdf.extract import (
    PdfLine,
    extract_pdf_lines,
    split_line_spans,
)


class PdfScreenplayParser(BaseParser):
    """Coordinate-clustering PDF screenplay parser using PyMuPDF."""

    def __init__(
        self,
        header_cutoff: float = 50.0,
        footer_cutoff: float = 740.0,
        cluster_tolerance: float = 8.0,
        max_pages: int = 500,
        span_gap_threshold: float | None = None,
    ) -> None:
        self.header_cutoff = header_cutoff
        self.footer_cutoff = footer_cutoff
        self.cluster_tolerance = cluster_tolerance
        self.max_pages = max_pages
        self.span_gap_threshold = span_gap_threshold

    def _split_line_spans(
        self, line: dict[str, Any]
    ) -> list[tuple[tuple[float, float, float, float], str]]:
        return split_line_spans(line, self.span_gap_threshold)

    def _extract_lines(self, pdf_bytes: bytes) -> list[PdfLine]:
        return extract_pdf_lines(
            pdf_bytes,
            header_cutoff=self.header_cutoff,
            footer_cutoff=self.footer_cutoff,
            max_pages=self.max_pages,
            span_gap_threshold=self.span_gap_threshold,
        )

    @staticmethod
    def _lines_are_dual_pair(a: PdfLine, b: PdfLine) -> bool:
        return lines_are_dual_pair(a, b)

    def _parse_dual_column(self, col_lines: list[PdfLine]) -> list[tuple[str, str]]:
        return parse_dual_column(col_lines, self.cluster_tolerance)

    def _find_dual_bands(
        self, page_lines: list[PdfLine]
    ) -> list[tuple[set[int], list[tuple[str, str]], list[tuple[str, str]]]]:
        return find_dual_bands(page_lines, self.cluster_tolerance)

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

        page_groups: dict[int, list[int]] = {}
        for global_idx, ln in enumerate(lines):
            page_groups.setdefault(ln.page, []).append(global_idx)

        dual_line_indices: set[int] = set()
        dual_bands_by_start: dict[
            int, tuple[list[tuple[str, str]], list[tuple[str, str]]]
        ] = {}

        for global_indices in page_groups.values():
            page_lines = [lines[idx] for idx in global_indices]
            for local_used, left_blocks, right_blocks in self._find_dual_bands(
                page_lines
            ):
                band_global = {global_indices[local_idx] for local_idx in local_used}
                dual_line_indices.update(band_global)
                dual_bands_by_start[min(band_global)] = (left_blocks, right_blocks)

        margin_lines = [
            ln for idx, ln in enumerate(lines) if idx not in dual_line_indices
        ] or lines

        clusters = cluster_x_positions(
            [ln.x0 for ln in margin_lines], self.cluster_tolerance
        )
        action_margin = clusters[0]
        dialogue_margin = clusters[1] if len(clusters) > 1 else action_margin + 36.0
        char_margin = (
            clusters[2]
            if len(clusters) > 2
            else (clusters[1] if len(clusters) > 1 else action_margin + 100.0)
        )

        char_candidates = [
            ln.x0 for ln in margin_lines if is_character_candidate(ln.text)
        ]
        if char_candidates:
            char_margin = sum(char_candidates) / len(char_candidates)
        non_action_non_char = [
            ln.x0
            for ln in margin_lines
            if ln.x0 > action_margin + self.cluster_tolerance
            and not is_character_candidate(ln.text)
            and not (ln.text.startswith("(") and ln.text.endswith(")"))
            and not is_transition(ln.text)
        ]
        if non_action_non_char:
            dialogue_margin = min(non_action_non_char)

        merged_blocks: list[tuple[str, str]] = []
        block_dual_flags: list[bool] = []
        in_dialogue = False
        prev_line: PdfLine | None = None
        prev_kind: str | None = None

        for idx, line in enumerate(lines):
            if idx in dual_bands_by_start:
                left_blocks, right_blocks = dual_bands_by_start[idx]
                for block in left_blocks:
                    merged_blocks.append(block)
                    block_dual_flags.append(False)
                for kind, text in right_blocks:
                    merged_blocks.append((kind, text))
                    block_dual_flags.append(kind == "character")
                in_dialogue = False
                prev_line = None
                prev_kind = None
                continue

            if idx in dual_line_indices:
                continue

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
                block_dual_flags.append(False)

            prev_line = line
            prev_kind = kind

        scenes = build_scenes_from_tagged_blocks(merged_blocks)
        _apply_dual_flags(scenes, merged_blocks, block_dual_flags)
        return ScriptDocument(metadata=raw.metadata, scenes=scenes)


def _apply_dual_flags(
    scenes: list[Any],
    merged_blocks: list[tuple[str, str]],
    block_dual_flags: list[bool],
) -> None:
    pending_char: str | None = None
    pending_has_lines = False
    pending_dual = False
    emitted_dual_flags: list[bool] = []

    def flush_pending() -> None:
        nonlocal pending_char, pending_has_lines, pending_dual
        if pending_char and pending_has_lines:
            emitted_dual_flags.append(pending_dual)
        pending_char = None
        pending_has_lines = False
        pending_dual = False

    for (kind, raw_text), is_dual in zip(
        merged_blocks, block_dual_flags, strict=True
    ):
        text = " ".join(raw_text.split()).strip()
        if not text:
            continue
        if kind in {"heading", "transition"}:
            flush_pending()
        elif kind == "character":
            flush_pending()
            name, _ = parse_character_cue(text)
            if name:
                pending_char = name
                pending_dual = is_dual
        elif kind == "parenthetical":
            pass
        elif kind == "dialogue":
            if pending_char:
                pending_has_lines = True
        else:
            flush_pending()

    flush_pending()

    dialogue_idx = 0
    for scene in scenes:
        prev_elem: SceneElement | None = None
        for elem in scene.elements:
            if isinstance(elem, Dialogue):
                if (
                    dialogue_idx < len(emitted_dual_flags)
                    and emitted_dual_flags[dialogue_idx]
                    and isinstance(prev_elem, Dialogue)
                ):
                    elem.dual = True
                dialogue_idx += 1
            prev_elem = elem
