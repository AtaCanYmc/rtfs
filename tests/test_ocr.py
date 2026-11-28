from __future__ import annotations

import builtins
import io
from unittest.mock import MagicMock, patch

import pymupdf
import pytest

from rtfs.parsers.pdf.ocr import tesseract_ocr_hook


def _make_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    pix.set_rect(pix.irect, (255, 0, 0))
    page.insert_image(pymupdf.Rect(10, 10, 50, 50), pixmap=pix)
    return doc.tobytes()


def test_tesseract_ocr_hook_raises_helpful_importerror_when_missing() -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"pytesseract", "PIL", "PIL.Image"}:
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="pyrtfs\\[ocr\\]"):
            tesseract_ocr_hook(b"%PDF-1.4")


def test_tesseract_ocr_hook_extracts_text_with_mocked_pytesseract() -> None:
    pdf_bytes = _make_image_only_pdf()
    fake_pytesseract = MagicMock()
    fake_pytesseract.image_to_string.return_value = "INT. LAB - NIGHT\n\nALICE\nHello.\n"
    fake_image_mod = MagicMock()
    fake_image_mod.open.side_effect = lambda buf: io.BytesIO(buf.read())

    fake_pil = MagicMock()
    fake_pil.Image = fake_image_mod

    with patch.dict(
        "sys.modules",
        {"pytesseract": fake_pytesseract, "PIL": fake_pil, "PIL.Image": fake_image_mod},
    ):
        text = tesseract_ocr_hook(pdf_bytes)

    assert "INT. LAB - NIGHT" in text
    assert fake_pytesseract.image_to_string.call_count == 1
