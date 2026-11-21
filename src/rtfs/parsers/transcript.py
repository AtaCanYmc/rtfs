from __future__ import annotations

import html
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import Action, Dialogue, RawScript, Scene, ScriptDocument
from rtfs.parsers.base import BaseParser, is_scene_heading, parse_character_cue, parse_heading

SPEAKER_COLON_RE = re.compile(r"^([A-Z][A-Z0-9\s.'()-]{1,35}):\s+(.+)$")


class TranscriptParser(BaseParser):
    """Plain-text and HTML subtitle/transcript parser."""

    def _extract_text(self, raw_content: str) -> str:
        if "<html" in raw_content.lower() or "full-script" in raw_content.lower():
            tree = HTMLParser(raw_content)
            node = tree.css_first("div.full-script") or tree.css_first("article") or tree.body
            if node:
                raw_inner = node.html or ""
                raw_inner = re.sub(r"<br\s*/?>", "\n", raw_inner, flags=re.IGNORECASE)
                raw_inner = re.sub(r"</p>", "\n", raw_inner, flags=re.IGNORECASE)
                clean = re.sub(r"<[^>]+>", "", raw_inner)
                return html.unescape(clean)
        return raw_content

    def parse(self, raw: RawScript) -> ScriptDocument:
        text_content = (
            raw.content.decode("utf-8", errors="replace")
            if isinstance(raw.content, bytes)
            else raw.content
        )
        plain = self._extract_text(text_content)

        scenes: list[Scene] = []
        current_scene = Scene(
            scene_number=1,
            heading="TRANSCRIPT",
            location=None,
            time_of_day=None,
            elements=[],
        )

        for raw_line in plain.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue

            if is_scene_heading(line):
                heading, loc, tod = parse_heading(line)
                if current_scene.elements:
                    scenes.append(current_scene)
                    current_scene = Scene(
                        scene_number=len(scenes) + 1,
                        heading=heading,
                        location=loc,
                        time_of_day=tod,
                        elements=[],
                    )
                else:
                    current_scene.heading = heading
                    current_scene.location = loc
                    current_scene.time_of_day = tod
                continue

            speaker_match = SPEAKER_COLON_RE.match(line)
            if speaker_match:
                raw_speaker, spoken = speaker_match.group(1), speaker_match.group(2).strip()
                char_name, mods = parse_character_cue(raw_speaker)
                paren: str | None = None
                if spoken.startswith("(") and ")" in spoken:
                    end_idx = spoken.find(")")
                    paren = spoken[1:end_idx].strip()
                    spoken = spoken[end_idx + 1 :].strip()
                current_scene.elements.append(
                    Dialogue(
                        character=char_name or "UNKNOWN",
                        modifiers=mods,
                        parenthetical=paren,
                        lines=spoken,
                    )
                )
            elif line.startswith("[") and line.endswith("]"):
                current_scene.elements.append(Action(text=line.strip("[]").strip()))
            else:
                current_scene.elements.append(
                    Dialogue(
                        character="TRANSCRIPT",
                        modifiers=[],
                        parenthetical=None,
                        lines=line,
                    )
                )

        if current_scene.elements:
            scenes.append(current_scene)

        return ScriptDocument(metadata=raw.metadata, scenes=scenes)
