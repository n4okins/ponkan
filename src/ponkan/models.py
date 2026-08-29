from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from .db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_col(primary_key: bool = False):
    return mapped_column(Uuid(as_uuid=True), primary_key=primary_key, default=uuid.uuid4)


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    default_prompt_lang: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    default_answer_lang: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    imports: Mapped[list[ImportSource]] = relationship(back_populates="material", cascade="all, delete-orphan")
    questions: Mapped[list[Question]] = relationship(back_populates="material", cascade="all, delete-orphan")


class ImportSource(Base):
    __tablename__ = "import_sources"
    __table_args__ = (
        CheckConstraint("kind IN ('google_sheets','csv_url')", name="ck_import_kind"),
    )

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), default="Import", nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str] = mapped_column(String(32), default="never", nullable=False)
    last_sync_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    material: Mapped[Material] = relationship(back_populates="imports")
    questions: Mapped[list[Question]] = relationship(back_populates="import_source")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("import_source_id", "external_key", name="uq_question_external_key"),
        CheckConstraint("question_type IN ('auto','card','multiple_choice')", name="ck_question_type"),
        Index("ix_question_material_active", "material_id", "archived_at", "is_enabled"),
    )

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    material_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    import_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("import_sources.id", ondelete="SET NULL")
    )
    external_key: Mapped[str | None] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    prompt_lang: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    answer_lang: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    material: Mapped[Material] = relationship(back_populates="questions")
    import_source: Mapped[ImportSource | None] = relationship(back_populates="questions")
    options: Mapped[list[QuestionOption]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="QuestionOption.position"
    )
    tags: Mapped[list[Tag]] = relationship(secondary="question_tags", back_populates="questions")


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (UniqueConstraint("question_id", "position", name="uq_question_option_position"),)

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped[Question] = relationship(back_populates="options")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    questions: Mapped[list[Question]] = relationship(secondary="question_tags", back_populates="tags")


class QuestionTag(Base):
    __tablename__ = "question_tags"

    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("learners.id", ondelete="CASCADE"), nullable=False
    )
    settings: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (Index("ix_review_state_due", "learner_id", "due_at"),)

    learner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    algorithm_version: Mapped[str] = mapped_column(String(32), default="ponkan-srs-v1", nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    stability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_rating: Mapped[int | None] = mapped_column(Integer)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avg_response_ms: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    mastery: Mapped[str] = mapped_column(String(24), default="weak", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 4", name="ck_review_rating"),
        Index("ix_review_event_time", "learner_id", "reviewed_at"),
    )

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    learner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("learners.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("study_sessions.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="choice", nullable=False)
    scheduled_days: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    stability_before: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    stability_after: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    difficulty_before: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    difficulty_after: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = uuid_col(primary_key=True)
    import_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("import_sources.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    seen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archived_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
