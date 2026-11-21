from __future__ import annotations

import re
from typing import ClassVar, Literal

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider

YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")


class SubsLikeScriptProvider(BaseProvider):
    name = "subslikescript"
    format = "transcript"
    BASE_URL = "https://subslikescript.com"
    allowed_hosts: ClassVar[set[str]] = {"subslikescript.com"}

    async def search(self, query: str) -> list[SearchResult]:
        cached = await self._get_cached_search(query)
        if cached is not None:
            return cached

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

            url = self.resolve_allowed_url(self.BASE_URL, href)
            if not url or url in seen_urls:
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
        await self._set_cached_search(query, top)
        return top

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        cached = await self._get_cached_raw(result.url)
        if cached is not None:
            return cached

        page_html = await self.http.get_text(result.url)
        tree = HTMLParser(page_html)

        script_div = tree.css_first("div.full-script")
        target_url = result.url
        if script_div is None and "/series/" in result.url:
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if "/series/" in href and "/season-" in href:
                    candidate = self.resolve_allowed_url(self.BASE_URL, href)
                    if candidate:
                        target_url = candidate
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
        await self._set_cached_raw(result.url, raw)
        return raw
