from __future__ import annotations

import io

import pymupdf


def tesseract_ocr_hook(pdf_bytes: bytes) -> str:
    """Render PDF pages via PyMuPDF and run local Tesseract OCR (requires pyrtfs[ocr])."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise ImportError(
            "Tesseract OCR requires optional dependencies. Install with: pip install 'pyrtfs[ocr]'"
        ) from exc

    pages_text: list[str] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
        for page in pdf_doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages_text.append(pytesseract.image_to_string(img))
    return "\n".join(pages_text)
