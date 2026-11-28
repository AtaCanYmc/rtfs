from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import pymupdf

from rtfs.core.cache import DiskCacheBackend, MemoryCacheBackend
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.fdx import FdxParser
from rtfs.parsers.fountain import FountainParser
from rtfs.parsers.html_screenplay import HtmlScreenplayParser
from rtfs.parsers.pdf.parser import PdfScreenplayParser, ScannedPdfError


def _make_scanned_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    pix.set_rect(pix.irect, (255, 0, 0))
    page.insert_image(pymupdf.Rect(10, 10, 50, 50), pixmap=pix)
    return doc.tobytes()


def bench_parsers() -> list[tuple[str, float, str]]:
    meta = ScriptMetadata(title="Bench", source="local", url="file://bench")
    fountain_raw = RawScript(
        content="INT. LAB - NIGHT\n\nALICE\nReady?\n\nBOB ^\nAlways.\n",
        content_type="fountain",
        metadata=meta,
    )
    fdx_raw = RawScript(
        content=(
            '<?xml version="1.0"?><FinalDraft DocumentType="Script" Version="5"><Content>'
            '<Paragraph Type="Scene Heading"><Text>INT. LAB - NIGHT</Text></Paragraph>'
            '<Paragraph Type="Character"><Text>ALICE</Text></Paragraph>'
            '<Paragraph Type="Dialogue"><Text>Ready?</Text></Paragraph>'
            "</Content></FinalDraft>"
        ),
        content_type="fdx",
        metadata=meta,
    )
    html_raw = RawScript(
        content=(
            "<td class='scrtext'><pre><b>INT. LAB - NIGHT</b>\n\n<b>ALICE</b>\nReady?\n</pre></td>"
        ),
        content_type="html",
        metadata=meta,
    )
    scanned_raw = RawScript(content=_make_scanned_pdf(), content_type="pdf", metadata=meta)

    results: list[tuple[str, float, str]] = []
    for name, fn in [
        ("FountainParser (dual dialogue)", lambda: FountainParser().parse(fountain_raw)),
        ("FdxParser (Final Draft v5 XML)", lambda: FdxParser().parse(fdx_raw)),
        ("HtmlScreenplayParser (IMSDb HTML)", lambda: HtmlScreenplayParser().parse(html_raw)),
    ]:
        t0 = time.perf_counter()
        for _ in range(100):
            doc = fn()
        ms = (time.perf_counter() - t0) * 1000 / 100
        results.append((name, round(ms, 3), f"{len(doc.scenes)} scene(s) OK"))

    t0 = time.perf_counter()
    for _ in range(20):
        try:
            PdfScreenplayParser().parse(scanned_raw)
        except ScannedPdfError:
            pass
    ms = (time.perf_counter() - t0) * 1000 / 20
    results.append(("PdfScreenplayParser (scanned PDF guard)", round(ms, 3), "ScannedPdfError OK"))
    return results


async def bench_caches() -> list[tuple[str, float, float]]:
    payload = b'{"title": "Bench", "scenes": []}'
    out: list[tuple[str, float, float]] = []

    mem = MemoryCacheBackend()
    t0 = time.perf_counter()
    for i in range(200):
        await mem.set(f"k{i}", payload)
    w_ms = (time.perf_counter() - t0) * 1000 / 200
    t0 = time.perf_counter()
    for i in range(200):
        await mem.get(f"k{i}")
    r_ms = (time.perf_counter() - t0) * 1000 / 200
    out.append(("memory://", round(w_ms, 4), round(r_ms, 4)))

    with tempfile.TemporaryDirectory() as tmp:
        disk = DiskCacheBackend(Path(tmp))
        t0 = time.perf_counter()
        for i in range(50):
            await disk.set(f"k{i}", payload)
        w_ms = (time.perf_counter() - t0) * 1000 / 50
        t0 = time.perf_counter()
        for i in range(50):
            await disk.get(f"k{i}")
        r_ms = (time.perf_counter() - t0) * 1000 / 50
        out.append(("disk:// (SQLite)", round(w_ms, 4), round(r_ms, 4)))
    return out


if __name__ == "__main__":
    print("=== Parser Benchmark ===")
    for name, ms, status in bench_parsers():
        print(f"{name}: {ms} ms/doc ({status})")
    print("=== Cache Benchmark ===")
    for name, w_ms, r_ms in asyncio.run(bench_caches()):
        print(f"{name}: write={w_ms} ms, read={r_ms} ms")
