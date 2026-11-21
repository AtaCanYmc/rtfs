from __future__ import annotations

import re
from typing import ClassVar

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider

EPISODE_CODE_RE = re.compile(r"\b(\d{1,2})x(\d{1,2})\b|\bS(\d{1,2})E(\d{1,2})\b", re.IGNORECASE)


class TVWritingProvider(BaseProvider):
    name = "tvwriting"
    format = "screenplay"
    BASE_URL = "https://sites.google.com/site/tvwriting"
    allowed_hosts: ClassVar[set[str]] = {
        "sites.google.com",
        "drive.google.com",
        "docs.google.com",
    }

    async def search(self, query: str) -> list[SearchResult]:
        cached = await self._get_cached_search(query)
        if cached is not None:
            return cached

        html_text = await self.http.get_text(
            self.BASE_URL,
            params={"q": query},
        )
        tree = HTMLParser(html_text)

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for link in tree.css("a"):
            href = link.attributes.get("href") or ""
            text = " ".join((link.text() or "").split()).strip()
            if not text or not href:
                continue
            is_pdf = ".pdf" in href.lower()
            is_script_page = "/tvwriting/" in href.lower()
            if not (is_pdf or is_script_page):
                continue

            score = float(fuzz.WRatio(query.lower(), text.lower()))
            if score < 45.0:
                continue

            url = self.resolve_allowed_url(self.BASE_URL + "/", href)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            ep_match = EPISODE_CODE_RE.search(text)
            season = int(ep_match.group(1) or ep_match.group(3)) if ep_match else None
            episode = int(ep_match.group(2) or ep_match.group(4)) if ep_match else None

            results.append(
                SearchResult(
                    title=text,
                    url=url,
                    source=self.name,
                    media_type="tv",
                    format="screenplay",
                    season=season,
                    episode=episode,
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

        target_url = result.url
        if not target_url.lower().split("?")[0].endswith(".pdf"):
            page_html = await self.http.get_text(target_url)
            tree = HTMLParser(page_html)
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if ".pdf" in href.lower():
                    candidate = self.resolve_allowed_url(self.BASE_URL + "/", href)
                    if candidate:
                        target_url = candidate
                        break

        pdf_bytes = await self.http.get_bytes(target_url)
        raw = RawScript(
            content=pdf_bytes,
            content_type="pdf",
            metadata=ScriptMetadata(
                title=result.title,
                year=result.year,
                media_type="tv",
                season=result.season,
                episode=result.episode,
                writers=result.writers,
                source=self.name,
                format="screenplay",
                url=target_url,
            ),
        )
        await self._set_cached_raw(result.url, raw)
        return raw
