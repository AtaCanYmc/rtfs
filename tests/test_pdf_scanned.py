from __future__ import annotations

import pymupdf
import pytest

from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.pdf.parser import PdfScreenplayParser, ScannedPdfError


def _make_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    # Insert a tiny 1x1 PNG image with no text
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    pix.set_rect(pix.irect, (255, 0, 0))
    page.insert_image(pymupdf.Rect(10, 10, 50, 50), pixmap=pix)
    return doc.tobytes()


def test_scanned_pdf_raises_structured_diagnostic() -> None:
    pdf_bytes = _make_image_only_pdf()
    raw = RawScript(
        content=pdf_bytes,
        content_type="pdf",
        metadata=ScriptMetadata(title="Scanned", source="local", url="file://scanned.pdf"),
    )
    with pytest.raises(ScannedPdfError) as exc_info:
        PdfScreenplayParser().parse(raw)

    err = exc_info.value
    assert err.page_count == 1
    assert err.image_count == 1
    assert "Scanned/image-only PDF" in str(err)


def test_scanned_pdf_uses_optional_ocr_hook() -> None:
    pdf_bytes = _make_image_only_pdf()
    raw = RawScript(
        content=pdf_bytes,
        content_type="pdf",
        metadata=ScriptMetadata(title="Scanned", source="local", url="file://scanned.pdf"),
    )
    called_with: list[bytes] = []

    def fake_ocr(data: bytes) -> str:
        called_with.append(data)
        return "INT. LAB - NIGHT\n\nALICE\nIt works.\n"

    doc = PdfScreenplayParser(ocr_hook=fake_ocr).parse(raw)
    assert called_with == [pdf_bytes]
    assert len(doc.scenes) >= 1
