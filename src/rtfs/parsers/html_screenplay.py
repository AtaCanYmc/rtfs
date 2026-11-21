from __future__ import annotations

import html
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from rtfs.core.models import RawScript, ScriptDocument
from rtfs.parsers.base import (
    BaseParser,
    build_scenes_from_tagged_blocks,
    cluster_x_positions,
    is_character_candidate,
    is_noise_line,
    is_scene_heading,
    is_transition,
)

TAG_STRIP_RE = re.compile(r"<[^>]+>")
BOLD_LINE_RE = re.compile(r"^(\s*)<b>(.*?)</b>(.*)$", re.IGNORECASE)


class HtmlScreenplayParser(BaseParser):
    """Parser for IMSDb and HTML `<pre>` screenplays supporting both `<b>` tags and indentation."""

    def _extract_pre_content(self, raw_html: str) -> str:
        tree = HTMLParser(raw_html)
        scrtext_pre = tree.css_first("td.scrtext pre")
        if scrtext_pre and scrtext_pre.html:
            inner = scrtext_pre.html
            inner = re.sub(r"^<pre[^>]*>", "", inner, flags=re.IGNORECASE)
            inner = re.sub(r"</pre>$", "", inner, flags=re.IGNORECASE)
            return inner

        pre = tree.css_first("pre")
        if pre and pre.html:
            inner = pre.html
            inner = re.sub(r"^<pre[^>]*>", "", inner, flags=re.IGNORECASE)
            inner = re.sub(r"</pre>$", "", inner, flags=re.IGNORECASE)
            return inner

        scrtext = tree.css_first("td.scrtext")
        if scrtext and scrtext.html:
            return scrtext.html

        return raw_html

    def parse(self, raw: RawScript) -> ScriptDocument:
        raw_html = (
            raw.content.decode("utf-8", errors="replace")
            if isinstance(raw.content, bytes)
            else raw.content
        )
        content = self._extract_pre_content(raw_html)
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
        raw_lines = content.splitlines()

        parsed_rows: list[tuple[int, bool, str]] = []
        for raw_line in raw_lines:
            expanded = raw_line.expandtabs(4)
            bold_match = BOLD_LINE_RE.match(expanded)
            is_bold = False
            if bold_match:
                leading = len(bold_match.group(1))
                bold_inner = TAG_STRIP_RE.sub("", bold_match.group(2))
                rest = TAG_STRIP_RE.sub("", bold_match.group(3))
                clean_text = html.unescape(f"{bold_inner}{rest}").strip()
                is_bold = bool(bold_inner.strip())
            else:
                plain = html.unescape(TAG_STRIP_RE.sub("", expanded))
                stripped = plain.lstrip(" ")
                leading = len(plain) - len(stripped)
                clean_text = stripped.strip()

            if not clean_text or is_noise_line(clean_text):
                continue
            parsed_rows.append((leading, is_bold, clean_text))

        if not parsed_rows:
            return ScriptDocument(metadata=raw.metadata, scenes=[])

        clusters = cluster_x_positions([float(r[0]) for r in parsed_rows], tolerance=3.0)
        action_indent = clusters[0]
        dialogue_indent = clusters[1] if len(clusters) > 1 else action_indent + 8.0

        char_indents = [
            float(indent)
            for indent, is_bold, text in parsed_rows
            if is_character_candidate(text) and (is_bold or indent > action_indent + 4)
        ]
        char_indent = (
            sum(char_indents) / len(char_indents)
            if char_indents
            else (clusters[2] if len(clusters) > 2 else dialogue_indent + 8.0)
        )

        blocks: list[tuple[str, str]] = []
        in_dialogue = False

        for indent, is_bold, text in parsed_rows:
            if is_scene_heading(text):
                kind = "heading"
                in_dialogue = False
            elif is_transition(text) or (indent > char_indent + 10 and text.isupper()):
                kind = "transition"
                in_dialogue = False
            elif (
                text.startswith("(")
                and text.endswith(")")
                and (in_dialogue or indent > action_indent + 3)
            ):
                kind = "parenthetical"
            elif is_character_candidate(text) and (
                is_bold or indent >= max(dialogue_indent + 2, action_indent + 6)
            ):
                kind = "character"
                in_dialogue = True
            elif in_dialogue and indent > action_indent + 2:
                kind = "dialogue"
            else:
                kind = "action"
                in_dialogue = False

            blocks.append((kind, text))

        scenes = build_scenes_from_tagged_blocks(blocks)
        return ScriptDocument(metadata=raw.metadata, scenes=scenes)
