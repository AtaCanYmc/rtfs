from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urljoin

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider

YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")


class SubsLikeScriptProvider(BaseProvider):
    name = "subslikescript"
    format = "transcript"
    BASE_URL = "https://subslikescript.com"

    async def search(self, query: str) -> list[SearchResult]:
        cached = self.cache.get("search:subslikescript", query.lower()) if self.cache else None
        if cached is not None:
            return [SearchResult.model_validate(item) for item in cached]

        html_text = await self.http.get_text(
            f"{self.BASE_URL}/search",
            params={"q": query},
        )
        tree = HTMLParser(html_text)
        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for link in tree.css("a"):
            href = link.attributes.get("href") or ""
            if not (href.startswith("/movie/") or href.startswith("/series/")):
                continue
            text = " ".join((link.text() or "").split()).strip()
            if not text:
                continue

            year_match = YEAR_PAREN_RE.search(text)
            year = int(year_match.group(1)) if year_match else None
            clean_title = YEAR_PAREN_RE.sub("", text).strip()

            score = float(fuzz.WRatio(query.lower(), clean_title.lower()))
            if score < 45.0:
                continue

            url = urljoin(self.BASE_URL, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            media_type: Literal["movie", "tv"] = (
                "tv" if href.startswith("/series/") else "movie"
            )
            results.append(
                SearchResult(
                    title=clean_title,
                    url=url,
                    source=self.name,
                    media_type=media_type,
                    format="transcript",
                    year=year,
                    score=score,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        top = results[:15]
        if self.cache and top:
            self.cache.set("search:subslikescript", query.lower(), [r.model_dump() for r in top])
        return top

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        if self.cache:
            cached = self.cache.get("raw:subslikescript", result.url)
            if cached is not None:
                return RawScript.model_validate(cached)

        page_html = await self.http.get_text(result.url)
        tree = HTMLParser(page_html)

        # If result is a TV series index page, resolve first episode transcript page
        script_div = tree.css_first("div.full-script")
        target_url = result.url
        if script_div is None and "/series/" in result.url:
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if "/series/" in href and "/season-" in href:
                    target_url = urljoin(self.BASE_URL, href)
                    page_html = await self.http.get_text(target_url)
                    break

        raw = RawScript(
            content=page_html,
            content_type="text",
            metadata=ScriptMetadata(
                title=result.title,
                year=result.year,
                media_type=result.media_type,
                season=result.season,
                episode=result.episode,
                writers=result.writers,
                source=self.name,
                format="transcript",
                url=target_url,
            ),
        )
        if self.cache:
            self.cache.set("raw:subslikescript", result.url, raw.model_dump())
        return raw
