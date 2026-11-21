from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pymupdf as fitz

from rtfs.core.models import Dialogue, RawScript, SceneElement, ScriptDocument
from rtfs.parsers.base import (
    BaseParser,
    build_scenes_from_tagged_blocks,
    cluster_x_positions,
    is_character_candidate,
    is_noise_line,
    is_scene_heading,
    is_transition,
    parse_character_cue,
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
        spans = line.get("spans", [])
        if not spans:
            return []

        line_bbox = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
        sorted_spans = sorted(
            spans,
            key=lambda sp: float(sp.get("bbox", line_bbox)[0]),
        )

        groups: list[list[dict[str, Any]]] = []
        current_group: list[dict[str, Any]] = []
        last_non_ws_x1: float | None = None

        for span in sorted_spans:
            stext = str(span.get("text", ""))
            sbbox = span.get("bbox", line_bbox)
            sx0 = float(sbbox[0])
            sx1 = float(sbbox[2])
            font_size = float(span.get("size", 12.0))

            if not stext.strip():
                if current_group:
                    current_group.append(span)
                continue

            gap_threshold = (
                self.span_gap_threshold
                if self.span_gap_threshold is not None
                else max(20.0, font_size * 2.0)
            )
            if last_non_ws_x1 is not None and (sx0 - last_non_ws_x1) > gap_threshold:
                groups.append(current_group)
                current_group = [span]
            else:
                current_group.append(span)
            last_non_ws_x1 = sx1 if last_non_ws_x1 is None else max(last_non_ws_x1, sx1)

        if current_group:
            groups.append(current_group)

        results: list[tuple[tuple[float, float, float, float], str]] = []
        for group in groups:
            gtext = "".join(str(s.get("text", "")) for s in group).strip()
            non_ws = [s for s in group if str(s.get("text", "")).strip()]
            if not gtext or not non_ws:
                continue
            gx0 = min(float(s.get("bbox", line_bbox)[0]) for s in non_ws)
            gy0 = min(float(s.get("bbox", line_bbox)[1]) for s in non_ws)
            gx1 = max(float(s.get("bbox", line_bbox)[2]) for s in non_ws)
            gy1 = max(float(s.get("bbox", line_bbox)[3]) for s in non_ws)
            results.append(((gx0, gy0, gx1, gy1), gtext))

        return results

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
                        for (gx0, gy0, gx1, gy1), gtext in self._split_line_spans(line):
                            if gy0 < self.header_cutoff or gy1 > self.footer_cutoff:
                                continue
                            if is_noise_line(gtext):
                                continue
                            page_lines.append(
                                PdfLine(page_idx, gx0, gy0, gx1, gy1, gtext)
                            )

                page_lines.sort(key=lambda ln: (round(ln.y0, 1), ln.x0))
                extracted.extend(page_lines)
        finally:
            doc.close()
        return extracted

    @staticmethod
    def _lines_are_dual_pair(a: PdfLine, b: PdfLine) -> bool:
        if a.page != b.page:
            return False
        y_overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
        if y_overlap < 0.4 * min(a.height, b.height):
            return False
        left, right = (a, b) if a.x0 <= b.x0 else (b, a)
        if left.x1 > right.x0 + 2.0:
            return False
        if (right.x0 - left.x0) < 40.0:
            return False
        return True

    def _parse_dual_column(self, col_lines: list[PdfLine]) -> list[tuple[str, str]]:
        if not col_lines:
            return []
        ordered = sorted(col_lines, key=lambda ln: (round(ln.y0, 1), ln.x0))
        non_cue_x0s = [
            ln.x0
            for ln in ordered
            if not is_character_candidate(ln.text)
            and not (ln.text.strip().startswith("(") and ln.text.strip().endswith(")"))
        ]
        col_dialogue_x0 = (
            min(non_cue_x0s) if non_cue_x0s else min(ln.x0 for ln in ordered)
        )

        blocks: list[tuple[str, str]] = []
        in_dialogue = False
        has_dialogue_for_turn = False
        first_cue_x0: float | None = None
        wrap_step: float | None = None
        prev_line: PdfLine | None = None
        prev_kind: str | None = None

        for ln in ordered:
            text = ln.text.strip()
            if is_scene_heading(text) or is_transition(text):
                return []

            if not in_dialogue:
                if is_character_candidate(text):
                    kind = "character"
                    in_dialogue = True
                    has_dialogue_for_turn = False
                    first_cue_x0 = ln.x0
                else:
                    kind = "action"
            else:
                if text.startswith("(") and text.endswith(")"):
                    kind = "parenthetical"
                elif (
                    has_dialogue_for_turn
                    and is_character_candidate(text)
                    and not text.endswith(("!", "?"))
                    and (
                        ln.x0 >= col_dialogue_x0 + 12.0
                        or (
                            first_cue_x0 is not None
                            and abs(ln.x0 - first_cue_x0) <= self.cluster_tolerance
                            and prev_line is not None
                            and (
                                (ln.y0 - prev_line.y1) > 0.1 * prev_line.height
                                or (
                                    wrap_step is not None
                                    and (ln.y0 - prev_line.y0) > wrap_step * 1.15
                                )
                            )
                        )
                    )
                ):
                    kind = "character"
                    has_dialogue_for_turn = False
                else:
                    kind = "dialogue"
                    has_dialogue_for_turn = True

            if prev_line is not None and kind in {"parenthetical", "dialogue"}:
                step = ln.y0 - prev_line.y0
                if step > 0.0 and (
                    wrap_step is None or (prev_kind == "dialogue" and kind == "dialogue")
                ):
                    wrap_step = step if wrap_step is None else min(wrap_step, step)

            if (
                prev_line is not None
                and prev_kind == kind
                and kind in {"dialogue", "parenthetical"}
                and abs(prev_line.x0 - ln.x0) <= self.cluster_tolerance
                and (ln.y0 - prev_line.y1) < 1.5 * prev_line.height
            ):
                last_kind, last_text = blocks[-1]
                blocks[-1] = (last_kind, f"{last_text} {text}")
            else:
                blocks.append((kind, text))

            prev_line = ln
            prev_kind = kind

        if any(kind == "action" for kind, _ in blocks):
            return []

        has_valid_turn = False
        pending_char = False
        for kind, _ in blocks:
            if kind == "character":
                pending_char = True
            elif kind == "dialogue" and pending_char:
                has_valid_turn = True

        return blocks if has_valid_turn else []

    def _find_dual_bands(
        self, page_lines: list[PdfLine]
    ) -> list[tuple[set[int], list[tuple[str, str]], list[tuple[str, str]]]]:
        n = len(page_lines)
        if n < 2:
            return []

        pairs: list[tuple[int, int, PdfLine, PdfLine, float, float, float]] = []
        for i in range(n):
            for j in range(i + 1, n):
                if not self._lines_are_dual_pair(page_lines[i], page_lines[j]):
                    continue
                left_idx, right_idx = (
                    (i, j)
                    if page_lines[i].x0 <= page_lines[j].x0
                    else (j, i)
                )
                left_ln = page_lines[left_idx]
                right_ln = page_lines[right_idx]
                pair_min_y0 = min(left_ln.y0, right_ln.y0)
                pair_max_y1 = max(left_ln.y1, right_ln.y1)
                avg_h = (left_ln.height + right_ln.height) / 2.0
                pairs.append(
                    (
                        min(left_idx, right_idx),
                        max(left_idx, right_idx),
                        left_ln,
                        right_ln,
                        pair_min_y0,
                        pair_max_y1,
                        avg_h,
                    )
                )

        if not pairs:
            return []

        pairs.sort(key=lambda p: (p[0], p[1]))

        raw_bands: list[dict[str, Any]] = []
        for (
            p_min_idx,
            p_max_idx,
            p_left,
            p_right,
            p_min_y0,
            p_max_y1,
            p_avg_h,
        ) in pairs:
            pair_has_non_cue = not (
                is_character_candidate(p_left.text)
                and is_character_candidate(p_right.text)
            )
            if not raw_bands:
                raw_bands.append(
                    {
                        "start": p_min_idx,
                        "end": p_max_idx,
                        "max_left_x1": p_left.x1,
                        "min_right_x0": p_right.x0,
                        "min_left_x0": p_left.x0,
                        "max_left_x0": p_left.x0,
                        "max_right_x0": p_right.x0,
                        "max_y1": p_max_y1,
                        "heights": [p_avg_h],
                        "has_non_cue": pair_has_non_cue,
                    }
                )
                continue

            cur = raw_bands[-1]
            cand_max_left_x1 = max(cur["max_left_x1"], p_left.x1)
            cand_min_right_x0 = min(cur["min_right_x0"], p_right.x0)
            cand_min_left_x0 = min(cur["min_left_x0"], p_left.x0)
            cand_max_left_x0 = max(cur["max_left_x0"], p_left.x0)
            cand_max_right_x0 = max(cur["max_right_x0"], p_right.x0)
            avg_h = sum(cur["heights"]) / len(cur["heights"])

            both_new_cues = (
                cur["has_non_cue"]
                and is_character_candidate(p_left.text)
                and is_character_candidate(p_right.text)
                and not p_left.text.strip().endswith(("!", "?"))
                and not p_right.text.strip().endswith(("!", "?"))
                and (p_min_y0 - cur["max_y1"]) > 0.1 * avg_h
            )

            can_merge = (
                not both_new_cues
                and cand_max_left_x1 <= cand_min_right_x0 + 2.0
                and (cand_min_right_x0 - cand_min_left_x0) >= 40.0
                and (cand_max_right_x0 - cand_min_right_x0) <= 100.0
                and (cand_max_left_x0 - cand_min_left_x0) <= 100.0
            )

            if can_merge:
                bridge_y1 = cur["max_y1"]
                for k in range(cur["end"] + 1, p_min_idx):
                    ln = page_lines[k]
                    if is_scene_heading(ln.text) or is_transition(ln.text):
                        can_merge = False
                        break
                    if ln.y0 - bridge_y1 > 0.6 * avg_h:
                        can_merge = False
                        break
                    gutter_mid = (cand_max_left_x1 + cand_min_right_x0) / 2.0
                    fits_left = ln.x1 <= cand_min_right_x0 + 2.0 and (
                        ln.x0 <= cand_max_left_x1 + 2.0 or ln.x0 < gutter_mid
                    )
                    fits_right = (
                        ln.x0 >= cand_max_left_x1 - 2.0 and ln.x0 >= gutter_mid
                    )
                    if fits_left and not fits_right:
                        cand_max_left_x1 = max(cand_max_left_x1, ln.x1)
                        cand_min_left_x0 = min(cand_min_left_x0, ln.x0)
                        cand_max_left_x0 = max(cand_max_left_x0, ln.x0)
                    elif fits_right and not fits_left:
                        cand_min_right_x0 = min(cand_min_right_x0, ln.x0)
                        cand_max_right_x0 = max(cand_max_right_x0, ln.x0)
                    else:
                        can_merge = False
                        break
                    if (
                        cand_max_left_x1 > cand_min_right_x0 + 2.0
                        or (cand_min_right_x0 - cand_min_left_x0) < 40.0
                        or (cand_max_right_x0 - cand_min_right_x0) > 100.0
                        or (cand_max_left_x0 - cand_min_left_x0) > 100.0
                    ):
                        can_merge = False
                        break
                    bridge_y1 = max(bridge_y1, ln.y1)
                if can_merge and (p_min_y0 - bridge_y1) > 0.6 * avg_h:
                    can_merge = False

            if can_merge:
                cur["start"] = min(cur["start"], p_min_idx)
                cur["end"] = max(cur["end"], p_max_idx)
                cur["max_left_x1"] = cand_max_left_x1
                cur["min_right_x0"] = cand_min_right_x0
                cur["min_left_x0"] = cand_min_left_x0
                cur["max_left_x0"] = cand_max_left_x0
                cur["max_right_x0"] = cand_max_right_x0
                cur["max_y1"] = max(cur["max_y1"], p_max_y1)
                cur["heights"].append(p_avg_h)
                cur["has_non_cue"] = cur["has_non_cue"] or pair_has_non_cue
            else:
                raw_bands.append(
                    {
                        "start": p_min_idx,
                        "end": p_max_idx,
                        "max_left_x1": p_left.x1,
                        "min_right_x0": p_right.x0,
                        "min_left_x0": p_left.x0,
                        "max_left_x0": p_left.x0,
                        "max_right_x0": p_right.x0,
                        "max_y1": p_max_y1,
                        "heights": [p_avg_h],
                        "has_non_cue": pair_has_non_cue,
                    }
                )

        confirmed: list[
            tuple[set[int], list[tuple[str, str]], list[tuple[str, str]]]
        ] = []
        prev_confirmed_end = -1

        def _side_step(indices: list[int]) -> float | None:
            steps = [
                page_lines[indices[idx]].y0 - page_lines[indices[idx - 1]].y0
                for idx in range(1, len(indices))
                if (page_lines[indices[idx]].y0 - page_lines[indices[idx - 1]].y0)
                > 1.0
            ]
            return min(steps) if steps else None

        for band_idx, band in enumerate(raw_bands):
            b_start: int = band["start"]
            b_end: int = band["end"]
            band_max_left_x1: float = band["max_left_x1"]
            band_min_right_x0: float = band["min_right_x0"]
            if band_max_left_x1 > band_min_right_x0 + 2.0:
                continue
            split_x = (band_max_left_x1 + band_min_right_x0) / 2.0
            next_band_start = (
                raw_bands[band_idx + 1]["start"]
                if band_idx + 1 < len(raw_bands)
                else n
            )

            left_indices: list[int] = []
            right_indices: list[int] = []
            valid_band = True
            for k in range(b_start, b_end + 1):
                if k <= prev_confirmed_end:
                    valid_band = False
                    break
                ln = page_lines[k]
                if is_scene_heading(ln.text) or is_transition(ln.text):
                    valid_band = False
                    break
                if ln.x1 <= split_x + 2.0:
                    left_indices.append(k)
                elif ln.x0 >= split_x - 2.0:
                    right_indices.append(k)
                else:
                    valid_band = False
                    break

            if not valid_band or not left_indices or not right_indices:
                continue

            # Expand upward for unpaired leading character cues / parentheticals
            for k in range(b_start - 1, prev_confirmed_end, -1):
                ln = page_lines[k]
                if is_scene_heading(ln.text) or is_transition(ln.text):
                    break
                if (
                    ln.x0 < band_max_left_x1 - 2.0
                    and ln.x1 > band_min_right_x0 + 2.0
                ):
                    break
                if ln.x1 <= band_min_right_x0 + 2.0 and ln.x0 < split_x:
                    is_left = True
                elif ln.x0 >= band_max_left_x1 - 2.0 and ln.x0 >= split_x - 2.0:
                    is_left = False
                else:
                    break
                stripped = ln.text.strip()
                is_paren = stripped.startswith("(") and stripped.endswith(")")
                if not (is_character_candidate(stripped) or is_paren):
                    break
                side_top = page_lines[left_indices[0] if is_left else right_indices[0]]
                if side_top.y0 - ln.y1 > 0.6 * ln.height:
                    break
                if is_left:
                    left_indices.insert(0, k)
                else:
                    right_indices.insert(0, k)

            # Expand downward for trailing wrapped dialogue lines
            for k in range(b_end + 1, next_band_start):
                ln = page_lines[k]
                if is_scene_heading(ln.text) or is_transition(ln.text):
                    break
                if (
                    ln.x0 < band_max_left_x1 - 2.0
                    and ln.x1 > band_min_right_x0 + 2.0
                ):
                    break
                if ln.x1 <= band_min_right_x0 + 2.0 and ln.x0 < split_x:
                    is_left = True
                elif ln.x0 >= band_max_left_x1 - 2.0 and ln.x0 >= split_x - 2.0:
                    is_left = False
                else:
                    break
                side_indices = left_indices if is_left else right_indices
                side_bot = page_lines[side_indices[-1]]
                if ln.y0 - side_bot.y1 > 0.25 * side_bot.height:
                    break
                step = _side_step(side_indices)
                if step is not None and (ln.y0 - side_bot.y0) > step * 1.3:
                    break
                stripped = ln.text.strip()
                is_paren = stripped.startswith("(") and stripped.endswith(")")
                if is_paren or ln.x0 <= side_bot.x0 + self.cluster_tolerance:
                    side_indices.append(k)
                else:
                    break

            left_blocks = self._parse_dual_column([page_lines[i] for i in left_indices])
            right_blocks = self._parse_dual_column(
                [page_lines[i] for i in right_indices]
            )
            if left_blocks and right_blocks:
                used = set(left_indices) | set(right_indices)
                confirmed.append((used, left_blocks, right_blocks))
                prev_confirmed_end = max(used)

        return confirmed

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

        # Ensure sensible margin hierarchy when a short snippet has fewer distinct columns
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

        return ScriptDocument(metadata=raw.metadata, scenes=scenes)
