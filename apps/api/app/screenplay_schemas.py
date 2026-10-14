import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from .schemas import Boundary


class Element(Boundary):
    kind: Literal["scene", "action", "character", "parenthetical", "dialogue", "transition"]
    text: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def formatting(self):
        if self.kind in {"scene", "character", "transition"}:
            self.text = self.text.upper()
        if self.kind == "scene" and not self.text.startswith(("INT.", "EXT.", "INT./EXT.", "EXT./INT.")):
            raise ValueError("Scene headings must start with INT. or EXT.")
        if self.kind == "parenthetical" and not (self.text.startswith("(") and self.text.endswith(")")):
            self.text = "(" + self.text.strip("()") + ")"
        return self


class Content(Boundary):
    elements: list[Element] = Field(min_length=1, max_length=50)
    material_ids: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def dialogue_cues(self):
        character = False
        for e in self.elements:
            if e.kind == "character":
                character = True
            elif e.kind in {"scene", "action", "transition"}:
                character = False
            elif e.kind in {"dialogue", "parenthetical"} and not character:
                raise ValueError("Dialogue and parentheticals need a preceding character cue")
        return self


class DraftOutput(Boundary):
    sections: list[Content] = Field(min_length=1, max_length=30)


class BreakdownOutput(Boundary):
    subsections: list[Content] = Field(min_length=4, max_length=6)


class SubsectionEdit(Boundary):
    id: str
    seconds: Literal[10, 15]
    content: Content


class SectionContent(Content):
    # A section can contain all six independently edited subsections.
    elements: list[Element] = Field(min_length=1, max_length=301)
    material_ids: list[str] = Field(default_factory=list, max_length=350)


class SectionEdit(Boundary):
    id: str
    content: SectionContent
    subsections: list[SubsectionEdit] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def duration(self):
        if self.subsections and (
            sum(s.seconds for s in self.subsections) != 60 or len({s.seconds for s in self.subsections}) != 1
        ):
            raise ValueError("Use six 10-second or four 15-second subsections per section")
        return self


class SaveScreenplay(Boundary):
    revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=200)
    reviewed_markdown: str = Field(min_length=1, max_length=200000)
    material_notes: dict[str, str] = Field(default_factory=dict, max_length=100)
    sections: list[SectionEdit] = Field(default_factory=list, max_length=30)


def source_hash(markdown, materials):
    context = [
        {
            "id": m["id"],
            "sha256": m.get("sha256"),
            "editor_notes": m.get("editor_notes", ""),
            "confirmation": m.get("confirmation", {}),
            "analysis": {k: v for k, v in m.get("analysis", {}).items() if k != "sections"},
        }
        for m in materials
    ]
    return hashlib.sha256(
        json.dumps({"markdown": markdown, "materials": context}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
