from __future__ import annotations

import re
from abc import ABC, abstractmethod

from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    SceneElement,
    ScriptDocument,
    Transition,
)

SCENE_HEADING_RE = re.compile(
    r"^(?:(?:\d+[A-Z]?\.?\s+)?)(INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|INT\.|EXT\.|INT\s|EXT\s)(.*)$",
    re.IGNORECASE,
)

TRANSITION_RE = re.compile(
    r"^(?:FADE\s+(?:IN|OUT|TO\s+BLACK)|CUT\s+TO|DISSOLVE\s+TO|SMASH\s+CUT\s+TO|"
    r"MATCH\s+CUT\s+TO|JUMP\s+CUT\s+TO|WIPE\s+TO|IRIS\s+OUT|BACK\s+TO|END\s+OF\s+\w+)"
    r"[:.]?$",
    re.IGNORECASE,
)

CONTINUED_RE = re.compile(
    r"^(?:\(?CONTINUED\)?(?:\s*:\s*(?:\(\d+\))?)?|\(MORE\)|CONTINUED:\s*\(\d+\))$",
    re.IGNORECASE,
)

PAGE_NUM_RE = re.compile(r"^\d+[A-Z]?\.$|^\d+$")
REVISION_RE = re.compile(
    r"(?:REV\.|REVISION|DRAFT|BLUE|PINK|YELLOW|GREEN|GOLDENROD)\s+\d{1,2}/\d{1,2}/\d{2,4}",
    re.IGNORECASE,
)

CHAR_MODIFIER_RE = re.compile(r"\(([^)]+)\)")


def parse_heading(raw_heading: str) -> tuple[str, str | None, str | None]:
    clean = " ".join(raw_heading.split()).upper()
    m = SCENE_HEADING_RE.match(clean)
    if not m:
        return clean, None, None
    body = m.group(2).strip(" .-–—")
    if " - " in body:
        parts = [p.strip() for p in body.rsplit(" - ", 1)]
        return clean, parts[0] or None, parts[1] or None
    if " -- " in body:
        parts = [p.strip() for p in body.rsplit(" -- ", 1)]
        return clean, parts[0] or None, parts[1] or None
    return clean, body or None, None


def is_scene_heading(text: str) -> bool:
    return bool(SCENE_HEADING_RE.match(text.strip()))


def is_transition(text: str) -> bool:
    stripped = text.strip()
    if TRANSITION_RE.match(stripped):
        return True
    return stripped.isupper() and stripped.endswith("TO:") and len(stripped) <= 35


def is_noise_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if CONTINUED_RE.match(stripped):
        return True
    if PAGE_NUM_RE.match(stripped):
        return True
    if REVISION_RE.search(stripped) and len(stripped) < 50:
        return True
    return False


def parse_character_cue(text: str) -> tuple[str, list[str]]:
    stripped = text.strip()
    modifiers = [m.strip() for m in CHAR_MODIFIER_RE.findall(stripped) if m.strip()]
    name = CHAR_MODIFIER_RE.sub("", stripped).strip(" :.-")
    return name, modifiers


def is_character_candidate(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 45:
        return False
    if is_scene_heading(stripped) or is_transition(stripped) or is_noise_line(stripped):
        return False
    if stripped.startswith("(") and stripped.endswith(")"):
        return False
    name, _ = parse_character_cue(stripped)
    if not name or any(ch.islower() for ch in name):
        return False
    if not any(ch.isalpha() for ch in name):
        return False
    if name.endswith(".") and not name.endswith(("MR.", "MRS.", "MS.", "DR.", "ST.", "JR.", "SR.")):
        return False
    return True


def cluster_x_positions(values: list[float], tolerance: float = 8.0) -> list[float]:
    """Cluster 1D left-margin coordinates within tolerance and return sorted cluster centers."""
    if not values:
        return []
    sorted_vals = sorted(values)
    clusters: list[list[float]] = [[sorted_vals[0]]]
    for val in sorted_vals[1:]:
        if abs(val - (sum(clusters[-1]) / len(clusters[-1]))) <= tolerance:
            clusters[-1].append(val)
        else:
            clusters.append([val])
    return [sum(c) / len(c) for c in clusters]


def build_scenes_from_tagged_blocks(
    blocks: list[tuple[str, str]],
) -> list[Scene]:
    """Convert classified blocks (kind, text) into canonical Scene AST list."""
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

    def flush_dialogue() -> None:
        nonlocal pending_char, pending_mods, pending_paren, pending_lines
        if pending_char and pending_lines:
            current_scene.elements.append(
                Dialogue(
                    character=pending_char,
                    modifiers=pending_mods,
                    parenthetical=pending_paren,
                    lines=" ".join(pending_lines).strip(),
                )
            )
        pending_char = None
        pending_mods = []
        pending_paren = None
        pending_lines = []

    for kind, raw_text in blocks:
        text = " ".join(raw_text.split()).strip()
        if not text:
            continue

        if kind == "heading":
            flush_dialogue()
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

        elif kind == "transition":
            flush_dialogue()
            current_scene.elements.append(Transition(text=text))

        elif kind == "character":
            flush_dialogue()
            name, mods = parse_character_cue(text)
            if name:
                pending_char = name
                pending_mods = mods

        elif kind == "parenthetical":
            clean_p = text.strip("()")
            if pending_char:
                if pending_lines:
                    pending_lines.append(f"({clean_p})")
                else:
                    pending_paren = (
                        f"{pending_paren}; {clean_p}" if pending_paren else clean_p
                    )
            else:
                current_scene.elements.append(Action(text=text))

        elif kind == "dialogue":
            if pending_char:
                pending_lines.append(text)
            else:
                current_scene.elements.append(Action(text=text))

        else:  # action
            flush_dialogue()
            if (
                current_scene.elements
                and isinstance(current_scene.elements[-1], Action)
            ):
                prev: SceneElement = current_scene.elements[-1]
                assert isinstance(prev, Action)
                prev.text = f"{prev.text} {text}"
            else:
                current_scene.elements.append(Action(text=text))

    flush_dialogue()
    if current_scene.elements or has_explicit_scene:
        scenes.append(current_scene)

    for idx, scene in enumerate(scenes, start=1):
        scene.scene_number = idx

    return scenes


class BaseParser(ABC):
    @abstractmethod
    def parse(self, raw: RawScript) -> ScriptDocument:
        raise NotImplementedError
