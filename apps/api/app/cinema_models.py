"""Immutable screenplay snapshots and durable, versioned video attempts."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .interview_database import InterviewBase
from .models import new_id, now


class CinemaProduction(InterviewBase):
    __tablename__ = "cinema_productions"
    __table_args__ = (UniqueConstraint("screenplay_id", "source_revision", name="uq_cinema_source"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    screenplay_id: Mapped[str] = mapped_column(ForeignKey("screenplays.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    interview_uid: Mapped[str] = mapped_column(String(36), index=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CinemaJob(InterviewBase):
    __tablename__ = "cinema_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    production_id: Mapped[str] = mapped_column(ForeignKey("cinema_productions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    subsection_id: Mapped[str | None] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    request: Mapped[dict] = mapped_column(JSON, default=dict)
    operation: Mapped[str | None] = mapped_column(String(300))
    output_key: Mapped[str | None] = mapped_column(String(700))
    frame_key: Mapped[str | None] = mapped_column(String(700))
    duration: Mapped[float | None] = mapped_column(Float)
    sha256: Mapped[str | None] = mapped_column(String(64))
    previewed: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
