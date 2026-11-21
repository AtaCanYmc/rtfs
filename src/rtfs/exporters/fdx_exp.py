from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from rtfs.core.models import Action, Dialogue, ScriptDocument, Transition

_ILLEGAL_XML_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]"
)


def _sanitize_xml(text: str) -> str:
    return _ILLEGAL_XML_RE.sub("", text)


def _append_paragraph(
    parent: ET.Element,
    para_type: str,
    text: str,
) -> ET.Element:
    para = ET.SubElement(parent, "Paragraph", {"Type": para_type})
    text_el = ET.SubElement(para, "Text")
    text_el.text = _sanitize_xml(text)
    return para


def _append_dialogue_paragraphs(parent: ET.Element, elem: Dialogue) -> None:
    mods = " ".join(f"({m})" for m in elem.modifiers)
    cue = f"{elem.character} {mods}".strip()
    _append_paragraph(parent, "Character", cue)

    if elem.parenthetical:
        paren = elem.parenthetical.strip()
        if not (paren.startswith("(") and paren.endswith(")")):
            paren = f"({paren})"
        _append_paragraph(parent, "Parenthetical", paren)

    _append_paragraph(parent, "Dialogue", elem.lines)


def export_fdx(doc: ScriptDocument) -> str:
    """Export canonical ScriptDocument AST to Final Draft (.fdx) XML."""
    root = ET.Element(
        "FinalDraft",
        {"DocumentType": "Script", "Template": "No", "Version": "5"},
    )

    if doc.metadata.title or doc.metadata.writers:
        title_page = ET.SubElement(root, "TitlePage")
        tp_content = ET.SubElement(title_page, "Content")
        if doc.metadata.title:
            para = ET.SubElement(
                tp_content,
                "Paragraph",
                {"Alignment": "Center", "Type": "Title"},
            )
            text_el = ET.SubElement(para, "Text")
            text_el.text = _sanitize_xml(doc.metadata.title)
        if doc.metadata.writers:
            para_by = ET.SubElement(tp_content, "Paragraph", {"Alignment": "Center"})
            text_by = ET.SubElement(para_by, "Text")
            text_by.text = "Written by"
            for writer in doc.metadata.writers:
                para_writer = ET.SubElement(
                    tp_content,
                    "Paragraph",
                    {"Alignment": "Center", "Type": "Writer"},
                )
                text_writer = ET.SubElement(para_writer, "Text")
                text_writer.text = _sanitize_xml(writer)

    content_el = ET.SubElement(root, "Content")

    for scene in doc.scenes:
        _append_paragraph(content_el, "Scene Heading", scene.heading)
        elements = scene.elements
        i = 0
        while i < len(elements):
            elem = elements[i]
            if isinstance(elem, Action):
                _append_paragraph(content_el, "Action", elem.text)
                i += 1
            elif isinstance(elem, Transition):
                _append_paragraph(content_el, "Transition", elem.text)
                i += 1
            elif isinstance(elem, Dialogue):
                if (
                    not elem.dual
                    and i + 1 < len(elements)
                    and isinstance(elements[i + 1], Dialogue)
                    and elements[i + 1].dual
                ):
                    wrapper = ET.SubElement(content_el, "Paragraph")
                    dual_el = ET.SubElement(wrapper, "DualDialogue")
                    _append_dialogue_paragraphs(dual_el, elem)
                    i += 1
                    while (
                        i < len(elements)
                        and isinstance(elements[i], Dialogue)
                        and elements[i].dual
                    ):
                        _append_dialogue_paragraphs(dual_el, elements[i])
                        i += 1
                elif elem.dual:
                    wrapper = ET.SubElement(content_el, "Paragraph")
                    dual_el = ET.SubElement(wrapper, "DualDialogue")
                    while (
                        i < len(elements)
                        and isinstance(elements[i], Dialogue)
                        and elements[i].dual
                    ):
                        _append_dialogue_paragraphs(dual_el, elements[i])
                        i += 1
                else:
                    _append_dialogue_paragraphs(content_el, elem)
                    i += 1
            else:
                i += 1

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'
