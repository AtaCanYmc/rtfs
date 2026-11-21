from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from rtfs.core.models import Action, Dialogue, ScriptDocument

SCENE_NUM_PREFIX_RE = re.compile(r"^\d+[A-Z]?\.?\s*")


@dataclass
class CharacterStat:
    character: str
    dialogue_turns: int
    word_count: int


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


def compute_stats(doc: ScriptDocument, top_n: int = 10) -> ScriptStats:
    int_scenes = 0
    ext_scenes = 0
    other_scenes = 0

    char_turns: Counter[str] = Counter()
    char_words: Counter[str] = Counter()
    dialogue_words = 0
    action_words = 0

    for scene in doc.scenes:
        h = SCENE_NUM_PREFIX_RE.sub("", scene.heading.upper().strip())
        if h.startswith("INT"):
            int_scenes += 1
        elif h.startswith("EXT"):
            ext_scenes += 1
        else:
            other_scenes += 1

        for elem in scene.elements:
            if isinstance(elem, Dialogue):
                words = len(elem.lines.split())
                dialogue_words += words
                char_turns[elem.character] += 1
                char_words[elem.character] += words
            elif isinstance(elem, Action):
                action_words += len(elem.text.split())

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
    )
