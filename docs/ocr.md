# OCR & Scanned PDFs (`pyrtfs[ocr]`)

[Back to docs index](README.md)

`rtfs` detects image-only / scanned PDFs automatically and supports both a plug-and-play local Tesseract adapter (`pyrtfs[ocr]`) and custom `ocr_hook` callables.

## Installation

```bash
pip install "pyrtfs[ocr]"
```

System requirement: `tesseract` binary must be installed on `PATH` (e.g. `brew install tesseract` on macOS or `apt-get install tesseract-ocr` on Debian/Ubuntu).

## CLI Usage

```bash
rtfs parse ./scanned_script.pdf --ocr --format fountain
```

## Scanned PDF Detection (`ScannedPdfError`)

When `PdfScreenplayParser` encounters a PDF with embedded images and zero extractable text lines (and no `ocr_hook` is provided), it raises `ScannedPdfError`:

```python
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.pdf.parser import PdfScreenplayParser, ScannedPdfError

raw = RawScript(
    content=open("scanned.pdf", "rb").read(),
    content_type="pdf",
    metadata=ScriptMetadata(title="Scanned", source="local", url="file://scanned.pdf"),
)

try:
    doc = PdfScreenplayParser().parse(raw)
except ScannedPdfError as exc:
    print(f"Scanned PDF: {exc.page_count} pages, {exc.image_count} images")
```

## Using `tesseract_ocr_hook` or a Custom `ocr_hook`

```python
from rtfs.parsers.pdf.ocr import tesseract_ocr_hook
from rtfs.parsers.pdf.parser import PdfScreenplayParser

parser = PdfScreenplayParser(ocr_hook=tesseract_ocr_hook)
doc = parser.parse(raw)
```

To use another OCR backend (e.g., AWS Textract, Google Cloud Vision), pass any `Callable[[bytes], str]` as `ocr_hook`.
