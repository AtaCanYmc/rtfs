from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urljoin

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptMetadata, SearchResult
from rtfs.providers.base import BaseProvider

YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
EPISODE_TAG_RE = re.compile(r"\bS(\d{1,2})E(\d{1,2})\b|\b(\d{1,2})x(\d{1,2})\b", re.IGNORECASE)


class ScriptSlugProvider(BaseProvider):
    name = "scriptslug"
    format = "screenplay"
    BASE_URL = "https://www.scriptslug.com"
    ASSETS_BASE = "https://assets.scriptslug.com/live/pdf/scripts"

    async def search(self, query: str) -> list[SearchResult]:
        cached = self.cache.get("search:scriptslug", query.lower()) if self.cache else None
        if cached is not None:
            return [SearchResult.model_validate(item) for item in cached]

        results: list[SearchResult] = []
        seen_urls: set[str] = set()

        html_text = await self.http.get_text(
            f"{self.BASE_URL}/scripts",
            params={"search": query},
        )
        tree = HTMLParser(html_text)

        for link in tree.css("a"):
            href = link.attributes.get("href") or ""
            if "/script/" not in href:
                continue
            url = urljoin(self.BASE_URL, href)
            if url in seen_urls:
                continue

            raw_text = " ".join((link.text() or "").split()).strip()
            slug = href.rstrip("/").split("/")[-1]
            year_match = YEAR_RE.search(raw_text) or YEAR_RE.search(slug)
            year = int(year_match.group(1)) if year_match else None

            title = raw_text
            if not title:
                title = re.sub(r"-(19|20)\d{2}$", "", slug).replace("-", " ").title()
            else:
                title = re.sub(r"\s*\(?(19|20)\d{2}\)?$", "", title).strip()

            score = float(fuzz.WRatio(query.lower(), title.lower()))
            if score < 45.0:
                continue

            ep_match = EPISODE_TAG_RE.search(raw_text) or EPISODE_TAG_RE.search(slug)
            media_type: Literal["movie", "tv"] = (
                "tv"
                if (ep_match or "episode" in raw_text.lower() or "pilot" in raw_text.lower())
                else "movie"
            )
            season = int(ep_match.group(1) or ep_match.group(3)) if ep_match else None
            episode = int(ep_match.group(2) or ep_match.group(4)) if ep_match else None

            seen_urls.add(url)
            results.append(
                SearchResult(
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
            )

        # Also support direct slug probing if HTML search yields nothing (e.g. client-rendered)
        if not results:
            slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
            if slug:
                candidate_url = f"{self.BASE_URL}/script/{slug}"
                try:
                    page = await self.http.get_text(candidate_url)
                    if ".pdf" in page or "assets.scriptslug.com" in page:
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
        if self.cache and top:
            self.cache.set("search:scriptslug", query.lower(), [r.model_dump() for r in top])
        return top

    async def fetch_raw(self, result: SearchResult) -> RawScript:
        if self.cache:
            cached = self.cache.get("raw:scriptslug", result.url)
            if cached is not None:
                return RawScript.model_validate(cached)

        pdf_url = result.url
        if not pdf_url.endswith(".pdf"):
            page_html = await self.http.get_text(result.url)
            tree = HTMLParser(page_html)
            found_pdf: str | None = None
            for link in tree.css("a"):
                href = link.attributes.get("href") or ""
                if ".pdf" in href:
                    found_pdf = urljoin(self.BASE_URL, href)
                    break
            if not found_pdf:
                m = re.search(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]+)?", page_html)
                if m:
                    found_pdf = m.group(0)
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
        if self.cache:
            self.cache.set("raw:scriptslug", result.url, raw.model_dump())
        return raw
