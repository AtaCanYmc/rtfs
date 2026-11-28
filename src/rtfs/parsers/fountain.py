from __future__ import annotations

import re

from rtfs.core.models import (
    Action,
    Dialogue,
    RawScript,
    Scene,
    ScriptDocument,
    Transition,
)
from rtfs.parsers.base import BaseParser, is_scene_heading, is_transition

_TITLE_KEY_RE = re.compile(
    r"^(Title|Credit|Author|Authors|Source|Draft date|Contact)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_FORCED_HEADING_RE = re.compile(r"^\.(?!\.)(.+)$")
_FORCED_TRANSITION_RE = re.compile(r"^>\s*(.+)$")
_CHAR_CUED_RE = re.compile(r"^([A-Z0-9][A-Z0-9 .'\-()]+?)(?:\s*(\^))?$")


class FountainParser(BaseParser):
    """Parse Fountain (.fountain) screenplay text into a canonical ScriptDocument."""

    def parse(self, raw: RawScript) -> ScriptDocument:
        text = (
            raw.content.decode("utf-8", errors="replace")
            if isinstance(raw.content, bytes)
            else raw.content
        )
        lines = text.splitlines()
        metadata = raw.metadata.model_copy()

        idx = 0
        # Parse optional Fountain title-page key: value block at top of file
        while idx < len(lines):
            line = lines[idx]
            if not line.strip():
                idx += 1
                break
            m = _TITLE_KEY_RE.match(line)
            if not m:
                break
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "title" and val:
                metadata.title = val
            elif key in {"author", "authors"} and val:
                metadata.writers = [w.strip() for w in re.split(r"[,&]", val) if w.strip()]
            idx += 1

        scenes: list[Scene] = []
        current_scene: Scene | None = None
        i = idx

        def ensure_scene(heading: str = "SCENE 1") -> Scene:
            nonlocal current_scene
            if current_scene is None:
                current_scene = Scene(scene_number=len(scenes) + 1, heading=heading)
                scenes.append(current_scene)
            return current_scene

        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue

            forced_h = _FORCED_HEADING_RE.match(stripped)
            if forced_h or is_scene_heading(stripped):
                heading = forced_h.group(1).strip() if forced_h else stripped
                current_scene = Scene(scene_number=len(scenes) + 1, heading=heading)
                scenes.append(current_scene)
                i += 1
                continue

            forced_t = _FORCED_TRANSITION_RE.match(stripped)
            if forced_t or is_transition(stripped):
                t_text = forced_t.group(1).strip() if forced_t else stripped
                ensure_scene().elements.append(Transition(text=t_text))
                i += 1
                continue

            # Character cue: uppercase line followed by non-empty dialogue/parenthetical
            prev_blank = i == 0 or not lines[i - 1].strip()
            next_non_blank = i + 1 < len(lines) and bool(lines[i + 1].strip())
            char_m = _CHAR_CUED_RE.match(stripped) if (prev_blank and next_non_blank) else None
            if char_m and any(c.isalpha() for c in char_m.group(1)):
                character = char_m.group(1).strip()
                dual = bool(char_m.group(2))
                i += 1
                parenthetical: str | None = None
                dlg_lines: list[str] = []
                while i < len(lines) and lines[i].strip():
                    d_line = lines[i].strip()
                    if (
                        d_line.startswith("(")
                        and d_line.endswith(")")
                        and not dlg_lines
                        and parenthetical is None
                    ):
                        parenthetical = d_line[1:-1].strip()
                    else:
                        dlg_lines.append(d_line)
                    i += 1
                if dlg_lines:
                    ensure_scene().elements.append(
                        Dialogue(
                            character=character,
                            parenthetical=parenthetical,
                            lines=" ".join(dlg_lines),
                            dual=dual,
                        )
                    )
                continue

            # Default: Action
            ensure_scene().elements.append(Action(text=stripped))
            i += 1

        return ScriptDocument(metadata=metadata, scenes=scenes)
