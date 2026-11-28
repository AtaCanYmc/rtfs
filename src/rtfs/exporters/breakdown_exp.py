from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from rtfs.core.models import Action, Dialogue, ScriptDocument
from rtfs.exporters.stats_exp import SCENE_NUM_PREFIX_RE
from rtfs.parsers.base import normalize_character_name

WORDS_PER_PAGE = 180.0


@dataclass
class SceneBreakdown:
    scene_number: int
    heading: str
    int_ext: str
    characters: list[str]
    estimated_minutes: float


@dataclass
class ProductionBreakdown:
    title: str
    total_scenes: int
    total_estimated_minutes: float
    locations: list[str]
    characters: list[str]
    scenes: list[SceneBreakdown]


def _classify_int_ext(heading: str) -> str:
    h = SCENE_NUM_PREFIX_RE.sub("", heading.upper().strip())
    if h.startswith(("INT", "İÇ", "IC")):
        return "INT"
    if h.startswith(("EXT", "DIŞ", "DIS")):
        return "EXT"
    return "OTHER"


def compute_breakdown(doc: ScriptDocument) -> ProductionBreakdown:
    """Build a production breakdown with locations, character continuity, and ~1pg/min estimates."""
    scene_items: list[SceneBreakdown] = []
    all_chars: set[str] = set()
    locations: list[str] = []
    seen_locs: set[str] = set()
    total_minutes = 0.0

    for scene in doc.scenes:
        if scene.heading not in seen_locs:
            seen_locs.add(scene.heading)
            locations.append(scene.heading)

        chars: set[str] = set()
        words = 0
        for el in scene.elements:
            if isinstance(el, Dialogue):
                chars.add(normalize_character_name(el.character))
                words += len(el.lines.split())
            elif isinstance(el, Action):
                words += len(el.text.split())

        all_chars.update(chars)
        est_min = max(0.25, round(words / WORDS_PER_PAGE, 2))
        total_minutes += est_min
        scene_items.append(
            SceneBreakdown(
                scene_number=scene.scene_number,
                heading=scene.heading,
                int_ext=_classify_int_ext(scene.heading),
                characters=sorted(chars),
                estimated_minutes=est_min,
            )
        )

    return ProductionBreakdown(
        title=doc.metadata.title,
        total_scenes=len(scene_items),
        total_estimated_minutes=round(total_minutes, 2),
        locations=locations,
        characters=sorted(all_chars),
        scenes=scene_items,
    )


def export_breakdown_json(doc: ScriptDocument) -> str:
    """Serialize a ProductionBreakdown to formatted JSON."""
    return json.dumps(asdict(compute_breakdown(doc)), indent=2, ensure_ascii=False)
