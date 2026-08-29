from __future__ import annotations

import json
import uuid

from mcp.server import MCPServer

from .db import SessionLocal
from .schemas import QuestionCreate
from .service import (
    create_question as svc_create_question,
    create_study_session as svc_create_study_session,
    default_learner,
    list_materials as svc_list_materials,
    question_to_dict,
    search_questions as svc_search_questions,
    stats as svc_stats,
    submit_review as svc_submit_review,
    sync_import as svc_sync_import,
)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def build_mcp_server() -> MCPServer:
    mcp = MCPServer(
        "Ponkan",
        instructions=(
            "Ponkan is a self-hosted study bank. Read tools are safe to use freely. "
            "Write tools change the user's materials or learning history; use them only when the user asks."
        ),
    )

    @mcp.tool()
    def list_materials() -> list[dict]:
        """List active study materials with question and due counts."""
        with SessionLocal() as db:
            learner = default_learner(db)
            return svc_list_materials(db, learner.id)

    @mcp.tool()
    def search_questions(
        query: str = "",
        material_ids: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search active questions by prompt, answer or explanation."""
        ids = [uuid.UUID(value) for value in material_ids or []]
        with SessionLocal() as db:
            learner = default_learner(db)
            return svc_search_questions(db, learner.id, ids or None, query, min(limit, 200))

    @mcp.tool()
    def create_study_session(
        material_ids: list[str],
        limit: int = 20,
        tags: list[str] | None = None,
    ) -> dict:
        """Create a prioritized SRS study session from one or more materials."""
        ids = [uuid.UUID(value) for value in material_ids]
        with SessionLocal() as db:
            learner = default_learner(db)
            return svc_create_study_session(db, learner, ids, limit, tags or [])

    @mcp.tool()
    def submit_review(
        question_id: str,
        rating: int,
        response_ms: int = 0,
        mode: str = "mcp",
        session_id: str | None = None,
    ) -> dict:
        """Record a review. rating: 1=again, 2=hard, 3=good, 4=easy."""
        with SessionLocal() as db:
            learner = default_learner(db)
            state = svc_submit_review(
                db,
                learner,
                uuid.UUID(question_id),
                rating,
                response_ms,
                mode,
                uuid.UUID(session_id) if session_id else None,
                {"source": "mcp"},
            )
            return {
                "mastery": state.mastery,
                "due_at": state.due_at,
                "stability": state.stability,
                "difficulty": state.difficulty,
                "reps": state.reps,
                "lapses": state.lapses,
                "streak": state.streak,
            }

    @mcp.tool()
    def create_question(
        material_id: str,
        prompt: str,
        answer: str,
        explanation: str = "",
        choices: list[str] | None = None,
        tags: list[str] | None = None,
        prompt_lang: str = "",
        answer_lang: str = "",
        question_type: str = "auto",
    ) -> dict:
        """Create one manual question in a material."""
        data = QuestionCreate(
            material_id=uuid.UUID(material_id),
            prompt=prompt,
            answer=answer,
            explanation=explanation,
            choices=choices or [],
            tags=tags or [],
            prompt_lang=prompt_lang,
            answer_lang=answer_lang,
            question_type=question_type,
        )
        with SessionLocal() as db:
            question = svc_create_question(db, data)
            if question is None:
                raise RuntimeError("question creation failed")
            return question_to_dict(question)

    @mcp.tool()
    def sync_import(import_source_id: str) -> dict:
        """Synchronize one already-registered Google Sheets/CSV import source."""
        with SessionLocal() as db:
            return svc_sync_import(db, uuid.UUID(import_source_id))

    @mcp.tool()
    def get_learning_stats() -> dict:
        """Return current learning statistics for the local learner."""
        with SessionLocal() as db:
            learner = default_learner(db)
            return svc_stats(db, learner)

    @mcp.resource("ponkan://materials")
    def materials_resource() -> str:
        """Current material catalog and due counts."""
        with SessionLocal() as db:
            learner = default_learner(db)
            return _json(svc_list_materials(db, learner.id))

    @mcp.resource("ponkan://stats")
    def stats_resource() -> str:
        """Current summary of the learner's SRS state."""
        with SessionLocal() as db:
            learner = default_learner(db)
            return _json(svc_stats(db, learner))

    @mcp.prompt()
    def daily_review(materials: str = "") -> str:
        """Prompt for conducting an interactive Ponkan review session."""
        material_note = f" Prefer materials matching: {materials}." if materials else ""
        return (
            "Use Ponkan tools to create a short review session. Ask one question at a time, wait for the "
            "user's answer, explain the result briefly, then call submit_review with an appropriate rating."
            + material_note
        )

    return mcp
