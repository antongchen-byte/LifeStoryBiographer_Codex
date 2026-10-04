from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .interview_database import InterviewBase
from .models import new_id, now


class InterviewConfig(InterviewBase):
    __tablename__ = "interview_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    avatar_id: Mapped[str] = mapped_column(String(36), default=new_id)
    avatar: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    genre: Mapped[str] = mapped_column(String(40))
    context: Mapped[dict] = mapped_column(JSON)
    markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InterviewChunk(InterviewBase):
    __tablename__ = "interview_context_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    config_id: Mapped[str] = mapped_column(ForeignKey("interview_configs.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON)


class InterviewSession(InterviewBase):
    __tablename__ = "interview_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    config_id: Mapped[str] = mapped_column(ForeignKey("interview_configs.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    active_token: Mapped[str | None] = mapped_column(String(36))
    busy_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InterviewTurn(InterviewBase):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "request_id", "role", name="uq_interview_request_role"),
        UniqueConstraint("session_id", "sequence", name="uq_interview_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text, default="")
    original_text: Mapped[str] = mapped_column(Text, default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    audio_key: Mapped[str | None] = mapped_column(String(500))
    audio_mime: Mapped[str | None] = mapped_column(String(100))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default="complete")
    error: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InterviewApproval(InterviewBase):
    __tablename__ = "approved_interviews"
    __table_args__ = (UniqueConstraint("session_id", "revision", name="uq_interview_approval"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    script: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
