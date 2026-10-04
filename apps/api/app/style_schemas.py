from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileCreate(Boundary):
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=3000)


class SourceCreate(Boundary):
    asset_id: str


class JobCreate(Boundary):
    request_id: str = Field(min_length=1, max_length=64)
    provider_consent: Literal[True]


class Publish(Boundary):
    request_id: str = Field(min_length=1, max_length=64)


class TurnInput(Boundary):
    role_scope: Literal["speaker", "turn"] | None = None
    speaker: str = Field(min_length=1, max_length=80)
    role: Literal["unknown", "interviewer", "participant", "other"] = "unknown"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def order(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("End must follow start")
        return self


class PatternInput(Boundary):
    category: Literal["question", "acknowledgment", "probe", "transition", "closing"]
    instruction: str = Field(min_length=1, max_length=2000)
    example: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)


class PatternReview(PatternInput):
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    anonymized_confirmed: bool = False


class TranscriptOutput(Boundary):
    turns: list[TurnInput] = Field(max_length=100)


class PatternOutput(Boundary):
    patterns: list[PatternInput] = Field(max_length=12)


class SpeakerRole(Boundary):
    across_sections: bool = False
    speaker: str = Field(min_length=1, max_length=80)
    role: Literal["interviewer", "participant", "other"]
