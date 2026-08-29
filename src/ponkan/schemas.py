from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

QuestionType = Literal["auto", "card", "multiple_choice"]
ImportKind = Literal["google_sheets", "csv_url"]


class MaterialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "general"
    default_prompt_lang: str = ""
    default_answer_lang: str = ""


class MaterialUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    default_prompt_lang: str | None = None
    default_answer_lang: str | None = None
    is_enabled: bool | None = None


class MaterialOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    category: str
    default_prompt_lang: str
    default_answer_lang: str
    is_enabled: bool
    archived_at: datetime | None
    question_count: int = 0
    due_count: int = 0

    model_config = {"from_attributes": True}


class ImportCreate(BaseModel):
    name: str = "Import"
    kind: ImportKind
    url: str = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    sync_now: bool = True


class ImportUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    config: dict[str, Any] | None = None
    is_enabled: bool | None = None


class ImportOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    name: str
    kind: str
    url: str
    config: dict[str, Any]
    is_enabled: bool
    last_synced_at: datetime | None
    last_sync_status: str
    last_sync_error: str

    model_config = {"from_attributes": True}


class QuestionCreate(BaseModel):
    material_id: uuid.UUID
    prompt: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    explanation: str = ""
    question_type: QuestionType = "auto"
    prompt_lang: str = ""
    answer_lang: str = ""
    choices: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class QuestionUpdate(BaseModel):
    prompt: str | None = None
    answer: str | None = None
    explanation: str | None = None
    question_type: QuestionType | None = None
    prompt_lang: str | None = None
    answer_lang: str | None = None
    choices: list[str] | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    is_enabled: bool | None = None


class OptionOut(BaseModel):
    text: str
    is_correct: bool
    position: int


class QuestionOut(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    import_source_id: uuid.UUID | None
    external_key: str | None
    prompt: str
    answer: str
    explanation: str
    question_type: str
    prompt_lang: str
    answer_lang: str
    metadata: dict[str, Any]
    is_enabled: bool
    archived_at: datetime | None
    choices: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    mastery: str | None = None
    due_at: datetime | None = None


class StudySessionCreate(BaseModel):
    material_ids: list[uuid.UUID] = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    tags: list[str] = Field(default_factory=list)


class StudyQuestion(BaseModel):
    id: uuid.UUID
    material_id: uuid.UUID
    prompt: str
    answer: str
    explanation: str
    question_type: str
    prompt_lang: str
    answer_lang: str
    choices: list[str]
    tags: list[str]
    mastery: str
    due_at: datetime | None


class StudySessionOut(BaseModel):
    session_id: uuid.UUID
    total_pool: int
    questions: list[StudyQuestion]


class ReviewCreate(BaseModel):
    question_id: uuid.UUID
    session_id: uuid.UUID | None = None
    rating: int = Field(ge=1, le=4)
    response_ms: int = Field(default=0, ge=0, le=300_000)
    mode: str = "choice"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewOut(BaseModel):
    mastery: str
    due_at: datetime
    stability: float
    difficulty: float
    reps: int
    lapses: int
    streak: int


class SyncResult(BaseModel):
    run_id: uuid.UUID
    status: str
    seen: int
    created: int
    updated: int
    archived: int
    error: str = ""


class StatsOut(BaseModel):
    active_questions: int
    learned_questions: int
    due_questions: int
    reviews_24h: int
    accuracy_24h: float
    mastery: dict[str, int]
