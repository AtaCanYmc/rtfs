from __future__ import annotations

from typing import Any

from rtfs.parsers.base import (
    is_character_candidate,
    is_scene_heading,
    is_transition,
)
from rtfs.parsers.pdf.extract import PdfLine


def lines_are_dual_pair(a: PdfLine, b: PdfLine) -> bool:
    """Return True if two PdfLine instances overlap vertically in distinct horizontal columns."""
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


def parse_dual_column(
    col_lines: list[PdfLine],
    cluster_tolerance: float = 8.0,
) -> list[tuple[str, str]]:
    """Parse one side (left or right) of a dual-dialogue band into tagged blocks."""
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
                        and abs(ln.x0 - first_cue_x0) <= cluster_tolerance
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
            and abs(prev_line.x0 - ln.x0) <= cluster_tolerance
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


def find_dual_bands(
    page_lines: list[PdfLine],
    cluster_tolerance: float = 8.0,
) -> list[tuple[set[int], list[tuple[str, str]], list[tuple[str, str]]]]:
    """Identify side-by-side simultaneous dialogue bands within a page's lines."""
    n = len(page_lines)
    if n < 2:
        return []

    pairs: list[tuple[int, int, PdfLine, PdfLine, float, float, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if not lines_are_dual_pair(page_lines[i], page_lines[j]):
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
            if is_paren or ln.x0 <= side_bot.x0 + cluster_tolerance:
                side_indices.append(k)
            else:
                break

        left_blocks = parse_dual_column(
            [page_lines[i] for i in left_indices],
            cluster_tolerance=cluster_tolerance,
        )
        right_blocks = parse_dual_column(
            [page_lines[i] for i in right_indices],
            cluster_tolerance=cluster_tolerance,
        )
        if left_blocks and right_blocks:
            used = set(left_indices) | set(right_indices)
            confirmed.append((used, left_blocks, right_blocks))
            prev_confirmed_end = max(used)

    return confirmed
