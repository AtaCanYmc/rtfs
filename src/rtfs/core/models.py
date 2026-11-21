from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScriptMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    title: str
    year: int | None = None
    media_type: Literal["movie", "tv"] = "movie"
    season: int | None = None
    episode: int | None = None
    writers: list[str] = Field(default_factory=list)
    source: str
    format: Literal["screenplay", "transcript"] = "screenplay"
    url: str


class SearchResult(BaseModel):
    model_config = ConfigDict(strict=True)

    title: str
    url: str
    source: str
    media_type: Literal["movie", "tv"] = "movie"
    format: Literal["screenplay", "transcript"] = "screenplay"
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    writers: list[str] = Field(default_factory=list)
    score: float = 0.0


class RawScript(BaseModel):
    model_config = ConfigDict(strict=True)

    content: bytes | str
    content_type: Literal["html", "pdf", "text"]
    metadata: ScriptMetadata


class Action(BaseModel):
    model_config = ConfigDict(strict=True)

    type: Literal["action"] = "action"
    text: str


class Dialogue(BaseModel):
    model_config = ConfigDict(strict=True)

    type: Literal["dialogue"] = "dialogue"
    character: str
    modifiers: list[str] = Field(default_factory=list)
    parenthetical: str | None = None
    lines: str


class Transition(BaseModel):
    model_config = ConfigDict(strict=True)

    type: Literal["transition"] = "transition"
    text: str


SceneElement = Annotated[
    Action | Dialogue | Transition,
    Field(discriminator="type"),
]


class Scene(BaseModel):
    model_config = ConfigDict(strict=True)

    scene_number: int
    heading: str
    location: str | None = None
    time_of_day: str | None = None
    elements: list[SceneElement] = Field(default_factory=list)


class ScriptDocument(BaseModel):
    model_config = ConfigDict(strict=True)

    metadata: ScriptMetadata
    scenes: list[Scene] = Field(default_factory=list)
