from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import MediaStatus, ProjectStatus


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Boundary):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class Register(Login):
    name: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str


class LoginRead(BaseModel):
    token: str
    user: UserRead


class ProjectCreate(Boundary):
    subject_name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=250)
    default_language: str = Field(default="en", min_length=2, max_length=16)


class ProjectUpdate(Boundary):
    subject_name: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=250)
    status: ProjectStatus | None = None

    @field_validator("subject_name", "status")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    role: str = "OWNER"
    media_count: int = 0


class MemberCreate(Boundary):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["SUBJECT", "EDITOR", "VIEWER"]


class UploadCreate(Boundary):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    ownership_declared: Literal[True]
    allow_duplicate: bool = False


class UploadPart(Boundary):
    part_number: int = Field(ge=1, le=10000)
    etag: str = Field(min_length=1, max_length=128, pattern=r'^"?[a-fA-F0-9-]+"?$')


class UploadStarted(BaseModel):
    asset_id: str
    status: MediaStatus
    part_size: int
    part_urls: list[str]
    uploaded_parts: list[UploadPart]


class UploadComplete(Boundary):
    parts: list[UploadPart] = Field(max_length=10000)


class MediaUpdate(Boundary):
    description: str | None = Field(default=None, max_length=5000)


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: MediaStatus
    checksum_sha256: str | None
    duration_ms: int | None
    width: int | None
    height: int | None
    description: str | None
    details: dict
    has_thumbnail: bool = False
    has_proxy: bool = False
    error: str | None
    created_at: datetime
