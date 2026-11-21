from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pymupdf as fitz

from rtfs.parsers.base import is_noise_line


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


def split_line_spans(
    line: dict[str, Any],
    span_gap_threshold: float | None = None,
) -> list[tuple[tuple[float, float, float, float], str]]:
    """Split a PyMuPDF line dict into horizontally separated span groups."""
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
            span_gap_threshold
            if span_gap_threshold is not None
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


def extract_pdf_lines(
    pdf_bytes: bytes,
    *,
    header_cutoff: float = 50.0,
    footer_cutoff: float = 740.0,
    max_pages: int = 500,
    span_gap_threshold: float | None = None,
) -> list[PdfLine]:
    """Extract noise-filtered PdfLine objects across pages up to max_pages."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted: list[PdfLine] = []
    try:
        for page_idx, page in enumerate(doc):
            if page_idx >= max_pages:
                break
            page_dict = page.get_text("dict")
            page_lines: list[PdfLine] = []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for (gx0, gy0, gx1, gy1), gtext in split_line_spans(
                        line, span_gap_threshold
                    ):
                        if gy0 < header_cutoff or gy1 > footer_cutoff:
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
