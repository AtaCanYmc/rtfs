from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, NoReturn
from xml.parsers import expat

from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    Transition,
)
from rtfs.parsers.base import BaseParser, parse_character_cue, parse_heading

_IGNORED_CHILD_TAGS = frozenset({"Text", "SceneProperties", "ScriptNote", "Summary"})
_CREDIT_HEADER_RE = re.compile(
    r"^(?:written|screenplay|teleplay|story)\s+by\s*:?$|^by\s*:?$",
    re.IGNORECASE,
)
_PREFIXED_TITLE_RE = re.compile(r"^title\s*:\s*(.+)$", re.IGNORECASE)
_PREFIXED_WRITER_RE = re.compile(
    r"^(?:written\s+by|screenplay\s+by|teleplay\s+by|story\s+by|authors?|writers?)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_WRITER_SPLIT_RE = re.compile(r"\s*(?:,|&|\band\b)\s*", re.IGNORECASE)
_NON_TITLE_OR_WRITER_RE = re.compile(
    r"(?:@|copyright|©|\ball\s+rights\s+reserved\b|\bdraft\b|\brev\.?\b|"
    r"\bphone\b|\bfax\b|\bemail\b|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$|^\d+\.?$)",
    re.IGNORECASE,
)


def _forbid_dtd(*_: Any) -> NoReturn:
    raise ValueError(
        "Forbidden XML construct: DOCTYPE and ENTITY declarations are not allowed"
    )


def _extract_paragraph_text(para: ET.Element) -> str:
    parts: list[str] = []
    for child in para:
        if child.tag != "Text":
            continue
        stack: list[tuple[ET.Element, bool]] = [(child, False)]
        while stack:
            node, visited = stack.pop()
            if visited:
                if node is not child and node.tail:
                    parts.append(node.tail)
            else:
                stack.append((node, True))
                if node.text:
                    parts.append(node.text)
                for sub in reversed(list(node)):
                    stack.append((sub, False))
    return " ".join("".join(parts).split()).strip()


def _split_writers(raw_writers: str) -> list[str]:
    return [part.strip() for part in _WRITER_SPLIT_RE.split(raw_writers) if part.strip()]


class FdxParser(BaseParser):
    """Safe stdlib-expat parser for Final Draft (.fdx) XML screenplays."""

    def _parse_xml_safely(self, content: bytes | str) -> ET.Element:
        parser = expat.ParserCreate()
        parser.buffer_text = True
        parser.StartDoctypeDeclHandler = _forbid_dtd
        parser.EntityDeclHandler = _forbid_dtd
        parser.UnparsedEntityDeclHandler = _forbid_dtd
        parser.NotationDeclHandler = _forbid_dtd
        parser.ExternalEntityRefHandler = _forbid_dtd

        builder = ET.TreeBuilder()
        parser.StartElementHandler = builder.start
        parser.EndElementHandler = builder.end
        parser.CharacterDataHandler = builder.data

        if isinstance(content, str):
            payload: bytes | str = content.lstrip("\ufeff")
            if not payload.strip():
                raise ValueError("Invalid FDX XML: empty content")
        else:
            payload = content
            if not payload:
                raise ValueError("Invalid FDX XML: empty content")

        try:
            parser.Parse(payload, True)
            root = builder.close()
        except (expat.ExpatError, UnicodeError) as exc:
            raise ValueError(f"Invalid FDX XML: {exc}") from exc

        if root is None or root.tag != "FinalDraft":
            tag = root.tag if root is not None else None
            raise ValueError(f"Expected <FinalDraft> root element, got {tag!r}")
        return root

    def _extract_title_page(self, root: ET.Element) -> tuple[str | None, list[str]]:
        title_page = root.find("TitlePage")
        if title_page is None:
            return None, []

        tp_content = title_page.find("Content")
        paragraphs = (
            tp_content.findall("Paragraph")
            if tp_content is not None
            else title_page.findall("Paragraph")
        )

        tp_title: str | None = None
        tp_writers: list[str] = []
        expecting_writers = False
        has_typed_writer = any(
            p.attrib.get("Type", "").strip().lower() == "writer"
            and _extract_paragraph_text(p)
            for p in paragraphs
        )

        for para in paragraphs:
            text = _extract_paragraph_text(para)
            if not text:
                expecting_writers = False
                continue

            ptype = para.attrib.get("Type", "").strip().lower()
            if ptype == "title":
                if tp_title is None:
                    tp_title = text
                expecting_writers = False
                continue

            if ptype == "writer":
                tp_writers.append(text)
                expecting_writers = False
                continue

            if ptype in {"author", "authors", "writers"}:
                tp_writers.extend(_split_writers(text))
                expecting_writers = False
                continue

            if has_typed_writer and _CREDIT_HEADER_RE.match(text):
                expecting_writers = False
                continue

            title_match = _PREFIXED_TITLE_RE.match(text)
            if title_match:
                if tp_title is None:
                    tp_title = title_match.group(1).strip()
                expecting_writers = False
                continue

            if _CREDIT_HEADER_RE.match(text):
                expecting_writers = True
                continue

            writer_match = _PREFIXED_WRITER_RE.match(text)
            if writer_match:
                rest = writer_match.group(1).strip()
                if rest:
                    if not has_typed_writer:
                        tp_writers.extend(_split_writers(rest))
                    expecting_writers = False
                else:
                    expecting_writers = not has_typed_writer
                continue

            if expecting_writers:
                if _NON_TITLE_OR_WRITER_RE.search(text):
                    expecting_writers = False
                elif not has_typed_writer:
                    tp_writers.extend(_split_writers(text))
                continue

            if tp_title is None and not _NON_TITLE_OR_WRITER_RE.search(text):
                tp_title = text

        deduped_writers: list[str] = []
        for writer in tp_writers:
            if writer not in deduped_writers:
                deduped_writers.append(writer)
        return tp_title, deduped_writers

    def parse(self, raw: RawScript) -> ScriptDocument:
        if raw.content_type != "fdx":
            raise ValueError(f"Expected content_type 'fdx', got {raw.content_type!r}")

        root = self._parse_xml_safely(raw.content)
        tp_title, tp_writers = self._extract_title_page(root)

        updates: dict[str, Any] = {}
        is_blank_or_untitled = (
            not raw.metadata.title or raw.metadata.title.strip().lower() == "untitled"
        )
        if is_blank_or_untitled and tp_title:
            updates["title"] = tp_title
        if not raw.metadata.writers and tp_writers:
            updates["writers"] = tp_writers
        metadata = raw.metadata.model_copy(update=updates) if updates else raw.metadata

        content_el = root.find("Content")
        if content_el is None:
            return ScriptDocument(metadata=metadata, scenes=[])

        scenes: list[Scene] = []
        current_scene = Scene(
            scene_number=1,
            heading="PROLOGUE",
            location=None,
            time_of_day=None,
            elements=[],
        )
        has_explicit_scene = False

        pending_char: str | None = None
        pending_mods: list[str] = []
        pending_paren: str | None = None
        pending_lines: list[str] = []

        def flush_dialogue(*, is_dual: bool = False) -> bool:
            nonlocal pending_char, pending_mods, pending_paren, pending_lines
            emitted = False
            if pending_char and pending_lines:
                current_scene.elements.append(
                    Dialogue(
                        character=pending_char,
                        modifiers=pending_mods,
                        parenthetical=pending_paren,
                        lines=" ".join(pending_lines).strip(),
                        dual=is_dual,
                    )
                )
                emitted = True
            pending_char = None
            pending_mods = []
            pending_paren = None
            pending_lines = []
            return emitted

        def flush_for_state(dual_state: list[int] | None) -> None:
            if dual_state is not None:
                if flush_dialogue(is_dual=dual_state[0] >= 1):
                    dual_state[0] += 1
            else:
                flush_dialogue(is_dual=False)

        def handle_paragraph(
            para: ET.Element,
            dual_state: list[int] | None,
        ) -> None:
            nonlocal current_scene, has_explicit_scene
            nonlocal pending_char, pending_mods, pending_paren

            text = _extract_paragraph_text(para)
            ptype = para.attrib.get("Type", "").strip().lower()
            if not text:
                return

            if ptype == "scene heading":
                flush_for_state(dual_state)
                heading, loc, tod = parse_heading(text)
                if not has_explicit_scene and not current_scene.elements:
                    current_scene.heading = heading
                    current_scene.location = loc
                    current_scene.time_of_day = tod
                    has_explicit_scene = True
                else:
                    if current_scene.elements or has_explicit_scene:
                        scenes.append(current_scene)
                    current_scene = Scene(
                        scene_number=len(scenes) + 1,
                        heading=heading,
                        location=loc,
                        time_of_day=tod,
                        elements=[],
                    )
                    has_explicit_scene = True

            elif ptype == "transition":
                flush_for_state(dual_state)
                current_scene.elements.append(Transition(text=text))

            elif ptype == "character":
                flush_for_state(dual_state)
                name, mods = parse_character_cue(text)
                if name:
                    pending_char = name
                    pending_mods = mods

            elif ptype == "parenthetical":
                clean_p = text.strip("()")
                if pending_char:
                    if pending_lines:
                        pending_lines.append(f"({clean_p})")
                    else:
                        pending_paren = (
                            f"{pending_paren}; {clean_p}"
                            if pending_paren
                            else clean_p
                        )
                else:
                    current_scene.elements.append(Action(text=text))

            elif ptype == "dialogue":
                if pending_char:
                    pending_lines.append(text)
                else:
                    current_scene.elements.append(Action(text=text))

            else:
                flush_for_state(dual_state)
                current_scene.elements.append(Action(text=text))

        stack: list[tuple[Any, ...]] = []
        for child in reversed(list(content_el)):
            if child.tag in {"SceneProperties", "ScriptNote", "Summary"}:
                continue
            if child.tag == "Paragraph":
                stack.append(("para", child, None))
            elif child.tag == "DualDialogue":
                stack.append(("dual", child))

        while stack:
            item = stack.pop()
            op = item[0]
            if op == "para":
                _, para, dual_state = item
                handle_paragraph(para, dual_state)
                for child in reversed(list(para)):
                    if child.tag in _IGNORED_CHILD_TAGS:
                        continue
                    if child.tag == "DualDialogue":
                        stack.append(("dual", child))
                    elif child.tag == "Paragraph":
                        stack.append(("para", child, dual_state))
            elif op == "dual":
                _, dual_el = item
                flush_dialogue(is_dual=False)
                dual_state = [0]
                stack.append(("dual_flush", dual_state))
                stack.append(("dual_walk", dual_el, dual_state))
            elif op == "dual_walk":
                _, node, dual_state = item
                for child in reversed(list(node)):
                    if child.tag in {"SceneProperties", "ScriptNote", "Summary"}:
                        continue
                    if child.tag in {"Column", "DualDialogueColumn"}:
                        stack.append(("dual_flush", dual_state))
                        stack.append(("dual_walk", child, dual_state))
                        stack.append(("dual_flush_enter", dual_state))
                    elif child.tag == "Paragraph":
                        stack.append(("para", child, dual_state))
            elif op in {"dual_flush", "dual_flush_enter"}:
                _, dual_state = item
                flush_for_state(dual_state)

        flush_dialogue(is_dual=False)
        if current_scene.elements or has_explicit_scene:
            scenes.append(current_scene)

        for idx, scene in enumerate(scenes, start=1):
            scene.scene_number = idx

        return ScriptDocument(metadata=metadata, scenes=scenes)
