from __future__ import annotations

import stat
from pathlib import Path

import fitz
import pytest

from rtfs.core.cache import DiskCacheBackend, NullCacheBackend
from rtfs.core.http import HttpClient, validate_public_http_url
from rtfs.core.models import RawScript, ScriptMetadata
from rtfs.parsers.pdf_screenplay import PdfScreenplayParser
from rtfs.providers.imsdb import IMSDbProvider
from rtfs.providers.scriptslug import ScriptSlugProvider
from rtfs.providers.subslikescript import SubsLikeScriptProvider
from rtfs.providers.tvwriting import TVWritingProvider


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1:8080/scripts/test.html",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal.pdf",
        "http://192.168.1.1/router.pdf",
        "http://[::1]:8000/test.pdf",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://service.internal/script.pdf",
        "file:///etc/passwd",
        "ftp://imsdb.com/scripts/Matrix.html",
    ],
)
def test_validate_public_http_url_blocks_ssrf_targets(blocked_url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_http_url(blocked_url)


def test_validate_public_http_url_allows_public_https() -> None:
    url = "https://imsdb.com/scripts/Matrix,-The.html"
    assert validate_public_http_url(url) == url


async def test_http_client_rejects_ssrf_before_network_call() -> None:
    async with HttpClient() as client:
        with pytest.raises(ValueError, match="Blocked"):
            await client.get_text("http://169.254.169.254/latest/meta-data/")


def test_provider_resolve_allowed_url_enforces_domain_allowlist() -> None:
    http = HttpClient()
    cache = NullCacheBackend()

    imsdb = IMSDbProvider(http, cache)
    assert (
        imsdb.resolve_allowed_url("https://imsdb.com", "/scripts/Matrix,-The.html")
        == "https://imsdb.com/scripts/Matrix,-The.html"
    )
    # Cross-origin or internal links embedded in scraped HTML must be rejected
    assert (
        imsdb.resolve_allowed_url(
            "https://imsdb.com",
            "https://evil.example.com/scripts/Matrix.html",
        )
        is None
    )
    assert (
        imsdb.resolve_allowed_url(
            "https://imsdb.com",
            "http://127.0.0.1/scripts/Matrix.html",
        )
        is None
    )

    slug = ScriptSlugProvider(http, cache)
    assert (
        slug.resolve_allowed_url(
            "https://www.scriptslug.com",
            "https://assets.scriptslug.com/live/pdf/scripts/the-matrix-1999.pdf",
        )
        == "https://assets.scriptslug.com/live/pdf/scripts/the-matrix-1999.pdf"
    )
    assert (
        slug.resolve_allowed_url(
            "https://www.scriptslug.com",
            "https://attacker.org/the-matrix-1999.pdf",
        )
        is None
    )

    tv = TVWritingProvider(http, cache)
    assert (
        tv.resolve_allowed_url(
            "https://sites.google.com/site/tvwriting/",
            "https://drive.google.com/file/d/123/pilot.pdf",
        )
        == "https://drive.google.com/file/d/123/pilot.pdf"
    )
    assert (
        tv.resolve_allowed_url(
            "https://sites.google.com/site/tvwriting/",
            "http://169.254.169.254/pilot.pdf",
        )
        is None
    )

    subs = SubsLikeScriptProvider(http, cache)
    assert (
        subs.resolve_allowed_url("https://subslikescript.com", "/movie/Matrix-133093")
        == "https://subslikescript.com/movie/Matrix-133093"
    )
    assert (
        subs.resolve_allowed_url("https://subslikescript.com", "https://evil.com/movie/1")
        is None
    )


def test_pdf_parser_enforces_max_pages_bound() -> None:
    doc = fitz.open()
    for idx in range(5):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), f"INT. ROOM {idx + 1} - DAY")
        page.insert_text((72, 130), "Action line.")
    pdf_bytes = doc.tobytes()
    doc.close()

    raw = RawScript(
        content=pdf_bytes,
        content_type="pdf",
        metadata=ScriptMetadata(
            title="Bounded PDF",
            source="scriptslug",
            url="https://www.scriptslug.com/script/bounded",
        ),
    )
    parser = PdfScreenplayParser(max_pages=2)
    parsed = parser.parse(raw)
    assert len(parsed.scenes) == 2


async def test_disk_cache_directory_permissions(tmp_path: Path) -> None:
    cache_dir = tmp_path / "secure_cache"
    cache = DiskCacheBackend(path=cache_dir)
    mode = stat.S_IMODE(cache_dir.stat().st_mode)
    assert mode == 0o700
    await cache.close()
