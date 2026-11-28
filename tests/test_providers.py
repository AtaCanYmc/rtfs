from __future__ import annotations

from unittest.mock import AsyncMock

from rtfs.core.cache import MemoryCacheBackend
from rtfs.core.http import HttpClient
from rtfs.providers.base import compute_title_similarity, normalize_title_for_match
from rtfs.providers.imsdb import IMSDbProvider
from rtfs.providers.scriptslug import ScriptSlugProvider
from rtfs.providers.subslikescript import SubsLikeScriptProvider
from rtfs.providers.tvwriting import TVWritingProvider


async def test_imsdb_provider_search_and_fetch_with_cache() -> None:
    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    search_html = """
    <html><body>
      <a href="/Movie Scripts/The Matrix Script.html">The Matrix Script</a>
      <a href="https://evil.example.com/Movie Scripts/The Matrix Script.html">The Matrix Script</a>
    </body></html>
    """
    landing_html = """
    <html><body>
      <a href="/writer.php?w=Lilly+Wachowski">Lilly Wachowski</a>
      <a href="/scripts/Matrix,-The.html">Read The Matrix Script</a>
    </body></html>
    """
    script_html = "<td class='scrtext'><pre><b>INT. ROOM - DAY</b></pre></td>"

    resp_mock = AsyncMock()
    resp_mock.text = search_html
    http.request.return_value = resp_mock
    http.get_text.side_effect = [landing_html, script_html]

    provider = IMSDbProvider(http, cache)

    # First search populates cache and ignores cross-origin link
    results = await provider.search("The Matrix")
    assert len(results) == 1
    assert results[0].title == "The Matrix"
    assert results[0].url == "https://imsdb.com/Movie Scripts/The Matrix Script.html"

    # Second search hits cache without calling http.request again
    cached_results = await provider.search("The Matrix")
    assert len(cached_results) == 1
    assert http.request.call_count == 1

    # fetch_raw resolves landing page -> /scripts/Matrix,-The.html and extracts writer
    raw = await provider.fetch_raw(results[0])
    assert raw.content_type == "html"
    assert raw.metadata.writers == ["Lilly Wachowski"]
    assert raw.metadata.url == "https://imsdb.com/scripts/Matrix,-The.html"

    # Second fetch_raw hits cache
    raw_cached = await provider.fetch_raw(results[0])
    assert raw_cached.metadata.url == raw.metadata.url
    assert http.get_text.call_count == 2


def test_imsdb_slug_to_script_url_handles_leading_articles() -> None:
    url = IMSDbProvider._slug_to_script_url("/Movie Scripts/The Grand Budapest Hotel Script.html")
    assert url == "https://imsdb.com/scripts/Grand-Budapest-Hotel,-The.html"


async def test_scriptslug_provider_search_and_fetch_pdf() -> None:
    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    search_html = """
    <html><body>
      <a href="/script/arrival-2016">Arrival (2016)</a>
      <a href="/script/succession-1x01-pilot-2018">Succession S01E01 Pilot (2018)</a>
    </body></html>
    """
    detail_html = """
    <html><body>
      <a href="https://assets.scriptslug.com/live/pdf/scripts/arrival-2016.pdf">Download PDF</a>
    </body></html>
    """
    http.get_text.side_effect = [search_html, detail_html]
    http.get_bytes.return_value = b"%PDF-1.4 fake-pdf-bytes"

    provider = ScriptSlugProvider(http, cache)
    results = await provider.search("Arrival")
    assert len(results) >= 1
    assert results[0].title == "Arrival"
    assert results[0].year == 2016
    assert results[0].media_type == "movie"

    raw = await provider.fetch_raw(results[0])
    assert raw.content_type == "pdf"
    assert raw.content == b"%PDF-1.4 fake-pdf-bytes"
    assert raw.metadata.url == "https://assets.scriptslug.com/live/pdf/scripts/arrival-2016.pdf"


async def test_tvwriting_provider_search_and_fetch() -> None:
    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    search_html = """
    <html><body>
      <a href="/site/tvwriting/us-drama/breaking-bad-1x01-pilot.pdf">Breaking Bad 1x01 - Pilot</a>
    </body></html>
    """
    http.get_text.return_value = search_html
    http.get_bytes.return_value = b"%PDF-1.4 pilot"

    provider = TVWritingProvider(http, cache)
    results = await provider.search("Breaking Bad")
    assert len(results) == 1
    assert results[0].media_type == "tv"
    assert results[0].season == 1
    assert results[0].episode == 1

    raw = await provider.fetch_raw(results[0])
    assert raw.content_type == "pdf"
    assert raw.content == b"%PDF-1.4 pilot"


async def test_subslikescript_provider_search_and_series_episode_resolution() -> None:
    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    search_html = """
    <html><body>
      <a href="/series/Chernobyl-7366338">Chernobyl (2019)</a>
    </body></html>
    """
    series_index_html = """
    <html><body>
      <a href="/series/Chernobyl-7366338/season-1/episode-1">1:23:45</a>
    </body></html>
    """
    episode_html = """
    <html><body>
      <div class="full-script">LEGASOV: What is the cost of lies?</div>
    </body></html>
    """
    http.get_text.side_effect = [search_html, series_index_html, episode_html]

    provider = SubsLikeScriptProvider(http, cache)
    results = await provider.search("Chernobyl")
    assert len(results) == 1
    assert results[0].title == "Chernobyl"
    assert results[0].year == 2019
    assert results[0].media_type == "tv"
    assert results[0].format == "transcript"

    raw = await provider.fetch_raw(results[0])
    assert raw.content_type == "text"
    assert "What is the cost of lies?" in str(raw.content)
    assert raw.metadata.url.endswith("/season-1/episode-1")


async def test_aggregator_direct_url_routing() -> None:
    from rtfs.core.aggregator import ScriptAggregator

    agg = ScriptAggregator(cache="memory://")
    res_pdf = agg._result_from_url("https://assets.scriptslug.com/live/pdf/scripts/dune-2021.pdf")
    assert res_pdf.source == "scriptslug"

    res_imsdb = agg._result_from_url("https://imsdb.com/scripts/Matrix,-The.html")
    assert res_imsdb.source == "imsdb"

    res_tv = agg._result_from_url("https://sites.google.com/site/tvwriting/pilot.pdf")
    assert res_tv.source == "tvwriting"
    assert res_tv.media_type == "tv"

    res_sub = agg._result_from_url("https://subslikescript.com/movie/Dune-1160419")
    assert res_sub.source == "subslikescript"
    assert res_sub.format == "transcript"
    await agg.close()


def test_title_similarity_handles_articles_and_rejects_stopword_false_positives() -> None:
    assert normalize_title_for_match("Matrix, The") == "matrix"
    assert normalize_title_for_match("The Matrix") == "matrix"

    assert compute_title_similarity("The Matrix", "Matrix, The") == 100.0
    assert compute_title_similarity("The Matrix", "The Matrix") == 100.0
    assert compute_title_similarity("The Matrix", "The Matrix Reloaded") < 100.0
    # Unrelated titles that only share "The" must not get an 85.5 WRatio boost
    assert compute_title_similarity("The Matrix", "The Honourable Woman") < 45.0


async def test_scriptslug_sitemap_and_fallback_paths() -> None:
    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset>
      <url><loc>https://www.scriptslug.com/script/dune-2021</loc></url>
      <url><loc>https://www.scriptslug.com/script/dune-2021</loc></url>
    </urlset>
    """
    http.get_text.return_value = sitemap_xml

    provider = ScriptSlugProvider(http, cache)
    results = await provider.search("Dune")
    assert len(results) == 1
    assert results[0].title == "Dune"
    assert results[0].year == 2021

    # Second search hits cache
    cached = await provider.search("Dune")
    assert len(cached) == 1
    assert http.get_text.call_count == 1


async def test_scriptslug_search_fallback_to_direct_slug_and_assets_pdf() -> None:
    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    # 1. sitemap fails, 2. /scripts?search= fails, 3. direct /script/arrival succeeds
    inline_html = (
        '<script>var pdf = "https://assets.scriptslug.com/live/pdf/scripts/arrival.pdf";</script>'
    )
    http.get_text.side_effect = [
        RuntimeError("sitemap 404"),
        RuntimeError("search 500"),
        inline_html,
        "<html><body>No pdf link here</body></html>",
    ]
    http.get_bytes.return_value = b"%PDF-1.4 fallback-bytes"

    provider = ScriptSlugProvider(http, cache)
    results = await provider.search("Arrival")
    assert len(results) == 1
    assert results[0].url == "https://www.scriptslug.com/script/arrival"

    # fetch_raw falls back to ASSETS_BASE/{slug}.pdf when HTML has no PDF link
    raw = await provider.fetch_raw(results[0])
    assert raw.content == b"%PDF-1.4 fallback-bytes"
    assert raw.metadata.url == "https://assets.scriptslug.com/live/pdf/scripts/arrival.pdf"

    # Second fetch_raw hits cache
    raw_cached = await provider.fetch_raw(results[0])
    assert raw_cached.metadata.url == raw.metadata.url
    assert http.get_bytes.call_count == 1


async def test_tvwriting_resolves_non_pdf_page_and_rejects_invalid_pdf() -> None:
    import pytest

    http = AsyncMock(spec=HttpClient)
    cache = MemoryCacheBackend()

    search_html = """
    <html><body>
      <a href="">Empty</a>
      <a href="/other/page.html">Unrelated</a>
      <a href="/tvwriting/pilot">Completely Different Show</a>
      <a href="/tvwriting/breaking-bad-1x01">Breaking Bad 1x01</a>
    </body></html>
    """
    detail_html = """
    <html><body>
      <a href="https://sites.google.com/site/tvwriting/breaking-bad-1x01.pdf">PDF</a>
    </body></html>
    """
    http.get_text.side_effect = [search_html, detail_html]
    http.get_bytes.return_value = b"%PDF-1.4 valid"

    provider = TVWritingProvider(http, cache)
    results = await provider.search("Breaking Bad")
    assert len(results) == 1
    assert results[0].season == 1
    assert results[0].episode == 1

    # Search cache hit
    cached = await provider.search("Breaking Bad")
    assert len(cached) == 1

    raw = await provider.fetch_raw(results[0])
    assert raw.content == b"%PDF-1.4 valid"

    # fetch_raw cache hit
    raw_cached = await provider.fetch_raw(results[0])
    assert raw_cached.content == b"%PDF-1.4 valid"

    # Invalid PDF payload raises ValueError
    http.get_bytes.return_value = b"<html>Not a PDF</html>"
    other = results[0].model_copy(update={"url": "https://sites.google.com/site/tvwriting/bad.pdf"})
    with pytest.raises(ValueError, match="valid PDF payload"):
        await provider.fetch_raw(other)


