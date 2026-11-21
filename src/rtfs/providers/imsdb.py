from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import quote, urljoin

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider


class IMSDbProvider(BaseProvider):
    name = "imsdb"
    format = "screenplay"
    BASE_URL = "https://imsdb.com"
    allowed_hosts: ClassVar[set[str]] = {"imsdb.com"}

    @staticmethod
    def _slug_to_script_url(href: str) -> str:
        m = re.search(r"/Movie Scripts/(.+?)\s+Script\.html", href, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            for article in ("The ", "A ", "An "):
                if title.startswith(article):
                    title = f"{title[len(article):]}, {article.strip()}"
                    break
            slug = re.sub(r"\s+", "-", title)
            return f"{IMSDbProvider.BASE_URL}/scripts/{slug}.html"
        return urljoin(IMSDbProvider.BASE_URL, href)

    async def search(self, query: str) -> list[SearchResult]:
        cached = await self._get_cached_search(query)
        if cached is not None:
            return cached

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        try:
            resp = await self.http.request(
                "POST",
                f"{self.BASE_URL}/search.php",
                data={"search_query": query, "submit": "Go!"},
            )
            html_text = resp.text
        except Exception:
            html_text = await self.http.get_text(f"{self.BASE_URL}/all-scripts.html")

        tree = HTMLParser(html_text)
        for node in tree.css("a"):
            href = node.attributes.get("href") or ""
            text = (node.text() or "").strip()
            if not text:
                continue
            if "/Movie Scripts/" in href or "/scripts/" in href:
                title = re.sub(r"\s+Script$", "", text, flags=re.IGNORECASE).strip()
                score = float(fuzz.WRatio(query.lower(), title.lower()))
                if score < 45.0:
                    continue
                url = self.resolve_allowed_url(self.BASE_URL, href)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        source=self.name,
                        media_type="movie",
                        format="screenplay",
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
        script_url = result.url
        writers = list(result.writers)

        if "/scripts/" not in result.url:
            tree = HTMLParser(page_html)
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if "/scripts/" in href and href.endswith(".html"):
                    candidate = self.resolve_allowed_url(
                        self.BASE_URL,
                        quote(href, safe="/:,.-_"),
                    )
                    if candidate:
                        script_url = candidate
                        break
            else:
                fallback = self.resolve_allowed_url(
                    self.BASE_URL,
                    self._slug_to_script_url(result.url),
                )
                if not fallback:
                    raise ValueError(f"Disallowed IMSDb script target for '{result.url}'")
                script_url = fallback

            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if "writer.php" in href:
                    w = (link.text() or "").strip()
                    if w and w not in writers:
                        writers.append(w)

            page_html = await self.http.get_text(script_url)

        raw = RawScript(
            content=page_html,
            content_type="html",
            metadata=ScriptMetadata(
                title=result.title,
                year=result.year,
                media_type=result.media_type,
                season=result.season,
                episode=result.episode,
                writers=writers,
                source=self.name,
                format="screenplay",
                url=script_url,
            ),
        )
        await self._set_cached_raw(result.url, raw)
        return raw
