from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from rtfs.core.models import Action, Dialogue, ScriptDocument
from rtfs.parsers.base import normalize_character_name

SCENE_NUM_PREFIX_RE = re.compile(r"^\d+[A-Z]?\.?\s*")


@dataclass
class CharacterStat:
    character: str
    dialogue_turns: int
    word_count: int


@dataclass
class ScenePacing:
    scene_number: int
    heading: str
    dialogue_words: int
    action_words: int
    total_words: int
    dialogue_density: float


@dataclass
class ScriptStats:
    title: str
    source: str
    format: str
    total_scenes: int
    int_scenes: int
    ext_scenes: int
    other_scenes: int
    int_ext_ratio: float
    dialogue_words: int
    action_words: int
    dialogue_to_action_ratio: float
    top_characters: list[CharacterStat]
    interactions: dict[str, dict[str, int]] = field(default_factory=dict)
    scene_pacing: list[ScenePacing] = field(default_factory=list)


def compute_stats(doc: ScriptDocument, top_n: int = 10) -> ScriptStats:
    int_scenes = 0
    ext_scenes = 0
    other_scenes = 0

    char_turns: Counter[str] = Counter()
    char_words: Counter[str] = Counter()
    interactions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    scene_pacing: list[ScenePacing] = []
    dialogue_words = 0
    action_words = 0

    for scene in doc.scenes:
        h = SCENE_NUM_PREFIX_RE.sub("", scene.heading.upper().strip())
        if h.startswith(("INT", "İÇ", "IC")):
            int_scenes += 1
        elif h.startswith(("EXT", "DIŞ", "DIS")):
            ext_scenes += 1
        else:
            other_scenes += 1

        scene_dlg_words = 0
        scene_act_words = 0
        scene_chars: set[str] = set()

        for elem in scene.elements:
            if isinstance(elem, Dialogue):
                words = len(elem.lines.split())
                dialogue_words += words
                scene_dlg_words += words
                char_name = normalize_character_name(elem.character)
                char_turns[char_name] += 1
                char_words[char_name] += words
                scene_chars.add(char_name)
            elif isinstance(elem, Action):
                words = len(elem.text.split())
                action_words += words
                scene_act_words += words

        for a, b in combinations(sorted(scene_chars), 2):
            interactions[a][b] += 1
            interactions[b][a] += 1

        total_scene_words = scene_dlg_words + scene_act_words
        density = round(scene_dlg_words / total_scene_words, 2) if total_scene_words > 0 else 0.0
        scene_pacing.append(
            ScenePacing(
                scene_number=scene.scene_number,
                heading=scene.heading,
                dialogue_words=scene_dlg_words,
                action_words=scene_act_words,
                total_words=total_scene_words,
                dialogue_density=density,
            )
        )

    int_ext_ratio = round(int_scenes / ext_scenes, 2) if ext_scenes > 0 else float(int_scenes)
    d_to_a_ratio = (
        round(dialogue_words / action_words, 2) if action_words > 0 else float(dialogue_words)
    )

    ranked_chars = sorted(
        char_turns.keys(),
        key=lambda c: (char_turns[c], char_words[c]),
        reverse=True,
    )[:top_n]

    top_characters = [
        CharacterStat(
            character=c,
            dialogue_turns=char_turns[c],
            word_count=char_words[c],
        )
        for c in ranked_chars
    ]

    return ScriptStats(
        title=doc.metadata.title,
        source=doc.metadata.source,
        format=doc.metadata.format,
        total_scenes=len(doc.scenes),
        int_scenes=int_scenes,
        ext_scenes=ext_scenes,
        other_scenes=other_scenes,
        int_ext_ratio=int_ext_ratio,
        dialogue_words=dialogue_words,
        action_words=action_words,
        dialogue_to_action_ratio=d_to_a_ratio,
        top_characters=top_characters,
        interactions={k: dict(v) for k, v in interactions.items()},
        scene_pacing=scene_pacing,
    )


def export_stats_mermaid(stats: ScriptStats) -> str:
    """Render character co-occurrence network and scene pacing as Mermaid diagrams."""
    lines = ["```mermaid", "flowchart LR"]
    seen_edges: set[tuple[str, str]] = set()
    for a, peers in sorted(stats.interactions.items()):
        for b, weight in sorted(peers.items()):
            edge = (min(a, b), max(a, b))
            if edge not in seen_edges:
                seen_edges.add(edge)
                lines.append(f"    {edge[0]} ---|{weight}| {edge[1]}")
    lines.append("```")

    if stats.scene_pacing:
        labels = ", ".join(f'"{p.scene_number}"' for p in stats.scene_pacing[:30])
        values = ", ".join(str(p.total_words) for p in stats.scene_pacing[:30])
        lines.extend(
            [
                "",
                "```mermaid",
                "xychart-beta",
                '    title "Scene Word Count Pacing"',
                f"    x-axis [{labels}]",
                '    y-axis "Words"',
                f"    bar [{values}]",
                "```",
            ]
        )
    return "\n".join(lines)
