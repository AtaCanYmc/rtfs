from __future__ import annotations

import re
from urllib.parse import urljoin

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider

EPISODE_CODE_RE = re.compile(r"\b(\d{1,2})x(\d{1,2})\b|\bS(\d{1,2})E(\d{1,2})\b", re.IGNORECASE)


class TVWritingProvider(BaseProvider):
    name = "tvwriting"
    format = "screenplay"
    BASE_URL = "https://sites.google.com/site/tvwriting"

    async def search(self, query: str) -> list[SearchResult]:
        cached = self.cache.get("search:tvwriting", query.lower()) if self.cache else None
        if cached is not None:
            return [SearchResult.model_validate(item) for item in cached]

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

            url = urljoin(self.BASE_URL + "/", href)
            if url in seen_urls:
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
        if self.cache and top:
            self.cache.set("search:tvwriting", query.lower(), [r.model_dump() for r in top])
        return top

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        if self.cache:
            cached = self.cache.get("raw:tvwriting", result.url)
            if cached is not None:
                return RawScript.model_validate(cached)

        target_url = result.url
        if not target_url.lower().split("?")[0].endswith(".pdf"):
            page_html = await self.http.get_text(target_url)
            tree = HTMLParser(page_html)
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if ".pdf" in href.lower():
                    target_url = urljoin(self.BASE_URL + "/", href)
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
        if self.cache:
            self.cache.set("raw:tvwriting", result.url, raw.model_dump())
        return raw
