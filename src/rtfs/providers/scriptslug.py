from __future__ import annotations

import re
from typing import ClassVar, Literal

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider, compute_title_similarity

YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
EPISODE_TAG_RE = re.compile(r"\bS(\d{1,2})E(\d{1,2})\b|\b(\d{1,2})x(\d{1,2})\b", re.IGNORECASE)
SITEMAP_LOC_RE = re.compile(r"<loc>(https://www\.scriptslug\.com/script/[^<\s]+)</loc>")


class ScriptSlugProvider(BaseProvider):
    name = "scriptslug"
    format = "screenplay"
    BASE_URL = "https://www.scriptslug.com"
    ASSETS_BASE = "https://assets.scriptslug.com/live/pdf/scripts"
    allowed_hosts: ClassVar[set[str]] = {"scriptslug.com"}

    def _candidate_from_slug_or_link(
        self,
        query: str,
        href: str,
        raw_text: str = "",
    ) -> SearchResult | None:
        url = self.resolve_allowed_url(self.BASE_URL, href)
        if not url:
            return None
        slug = href.rstrip("/").split("/")[-1]
        year_match = YEAR_RE.search(raw_text) or YEAR_RE.search(slug)
        year = int(year_match.group(1)) if year_match else None

        title = raw_text
        if not title:
            title = re.sub(r"-(19|20)\d{2}$", "", slug).replace("-", " ").title()
        else:
            title = re.sub(r"\s*\(?(19|20)\d{2}\)?$", "", title).strip()

        score = compute_title_similarity(query, title)
        if score < 50.0:
            return None

        ep_match = EPISODE_TAG_RE.search(raw_text) or EPISODE_TAG_RE.search(slug)
        media_type: Literal["movie", "tv"] = (
            "tv"
            if (ep_match or "episode" in raw_text.lower() or "pilot" in slug.lower())
            else "movie"
        )
        season = int(ep_match.group(1) or ep_match.group(3)) if ep_match else None
        episode = int(ep_match.group(2) or ep_match.group(4)) if ep_match else None

        return SearchResult(
            title=title or slug,
            url=url,
            source=self.name,
            media_type=media_type,
            format="screenplay",
            year=year,
            season=season,
            episode=episode,
            score=score,
        )

    async def search(self, query: str) -> list[SearchResult]:
        cached = await self._get_cached_search(query)
        if cached is not None:
            return cached

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        # Primary: ScriptSlug's sitemap-scripts.xml (or HTML links if returned by a mock/endpoint)
        try:
            payload = await self.http.get_text(f"{self.BASE_URL}/sitemap-scripts.xml")
        except Exception:
            try:
                payload = await self.http.get_text(
                    f"{self.BASE_URL}/scripts",
                    params={"search": query},
                )
            except Exception:
                payload = ""

        for loc_url in SITEMAP_LOC_RE.findall(payload):
            if loc_url in seen_urls:
                continue
            cand = self._candidate_from_slug_or_link(query, loc_url)
            if cand is not None:
                seen_urls.add(cand.url)
                results.append(cand)

        if "<a" in payload:
            tree = HTMLParser(payload)
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if "/script/" not in href:
                    continue
                raw_text = " ".join((link.text() or "").split()).strip()
                cand = self._candidate_from_slug_or_link(query, href, raw_text)
                if cand is not None and cand.url not in seen_urls:
                    seen_urls.add(cand.url)
                    results.append(cand)

        if not results:
            slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
            if slug:
                candidate_url = f"{self.BASE_URL}/script/{slug}"
                try:
                    page = await self.http.get_text(candidate_url)
                    if self._extract_pdf_url_from_html(page) is not None:
                        results.append(
                            SearchResult(
                                title=query.title(),
                                url=candidate_url,
                                source=self.name,
                                media_type="movie",
                                format="screenplay",
                                score=95.0,
                            )
                        )
                except Exception:
                    pass

        results.sort(key=lambda r: r.score, reverse=True)
        top = results[:15]
        await self._set_cached_search(query, top)
        return top

    def _extract_pdf_url_from_html(self, page_html: str) -> str | None:
        tree = HTMLParser(page_html)
        for link in tree.css("a"):
            href = link.attributes.get("href") or ""
            if ".pdf" in href.lower():
                candidate = self.resolve_allowed_url(self.BASE_URL, href)
                if candidate:
                    return candidate
        for m in re.finditer(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]+)?", page_html):
            candidate = self.resolve_allowed_url(self.BASE_URL, m.group(0))
            if candidate:
                return candidate
        return None

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        cached = await self._get_cached_raw(result.url)
        if cached is not None:
            return cached

        pdf_url = result.url
        if not pdf_url.endswith(".pdf"):
            page_html = await self.http.get_text(result.url)
            found_pdf = self._extract_pdf_url_from_html(page_html)
            if not found_pdf:
                slug = result.url.rstrip("/").split("/")[-1]
                found_pdf = f"{self.ASSETS_BASE}/{slug}.pdf"
            pdf_url = found_pdf

        pdf_bytes = await self.http.get_bytes(pdf_url)
        raw = RawScript(
            content=pdf_bytes,
            content_type="pdf",
            metadata=ScriptMetadata(
                title=result.title,
                year=result.year,
                media_type=result.media_type,
                season=result.season,
                episode=result.episode,
                writers=result.writers,
                source=self.name,
                format="screenplay",
                url=pdf_url,
            ),
        )
        await self._set_cached_raw(result.url, raw)
        return raw
