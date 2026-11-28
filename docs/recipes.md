# Recipes

[Back to docs index](README.md)

## 1. Stream JSONL Corpora for ML / NLP Pipelines

Export any parsed script to newline-delimited JSON (`JSONL`), one record per screenplay element:

```bash
rtfs parse ./script.fountain --format jsonl --output ./corpus.jsonl
```

In Python, stream records without buffering the full output string:

```python
from rtfs.core.client import RTFSClient
from rtfs.exporters.jsonl_exp import iter_jsonl

client = RTFSClient(cache="none://")
doc = client.parse_local("script.fountain")

for line in iter_jsonl(doc):
    process_record(line)
```

## 2. Compare Two Script Drafts (`rtfs diff`)

Generate a unified diff of scene headings and normalized dialogue lines between two local drafts:

```bash
rtfs diff draft_v1.fountain draft_v2.fdx
```

## 3. Parse Scanned PDFs with an OCR Hook

`PdfScreenplayParser` raises `ScannedPdfError` when a PDF contains images but zero extractable text. Supply an `ocr_hook(pdf_bytes: bytes) -> str` callable to route scanned pages through an OCR engine:

```python
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.pdf.parser import PdfScreenplayParser

def run_ocr(pdf_bytes: bytes) -> str:
    # Replace with pytesseract, AWS Textract, or another OCR backend
    return my_ocr_engine(pdf_bytes)

parser = PdfScreenplayParser(ocr_hook=run_ocr)
doc = parser.parse(
    RawScript(
        content=open("scanned.pdf", "rb").read(),
        content_type="pdf",
        metadata=ScriptMetadata(title="Scanned", source="local", url="file://scanned.pdf"),
    )
)
```

## 4. Register a Third-Party Provider Plugin

Expose a `BaseProvider` subclass in your package's `pyproject.toml` under `rtfs.providers`:

```toml
[project.entry-points."rtfs.providers"]
my_archive = "my_package.provider:MyArchiveProvider"
```

`ScriptAggregator` discovers and loads registered `rtfs.providers` entry points automatically on initialization.
