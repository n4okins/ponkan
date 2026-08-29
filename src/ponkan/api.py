from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import get_db
from .models import ImportSource, Material, Question, utcnow
from .schemas import (
    ImportCreate,
    ImportOut,
    ImportUpdate,
    MaterialCreate,
    MaterialOut,
    MaterialUpdate,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    ReviewCreate,
    ReviewOut,
    StatsOut,
    StudySessionCreate,
    StudySessionOut,
    SyncResult,
)
from .service import (
    create_question,
    create_study_session,
    default_learner,
    list_materials,
    question_to_dict,
    search_questions,
    stats,
    submit_review,
    sync_import,
    update_question,
)

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": "3.0.0"}


@router.get("/materials", response_model=list[MaterialOut])
def materials(db: Session = Depends(get_db)):
    learner = default_learner(db)
    return list_materials(db, learner.id)


@router.post("/materials", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
def material_create(data: MaterialCreate, db: Session = Depends(get_db)):
    material = Material(**data.model_dump())
    db.add(material)
    db.commit()
    db.refresh(material)
    return {
        **data.model_dump(),
        "id": material.id,
        "is_enabled": True,
        "archived_at": None,
        "question_count": 0,
        "due_count": 0,
    }


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def material_update(material_id: uuid.UUID, data: MaterialUpdate, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if material is None or material.archived_at is not None:
        raise HTTPException(404, "material not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(material, key, value)
    db.commit()
    learner = default_learner(db)
    return next(item for item in list_materials(db, learner.id) if item["id"] == material.id)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def material_archive(material_id: uuid.UUID, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if material is None or material.archived_at is not None:
        raise HTTPException(404, "material not found")
    material.archived_at = utcnow()
    material.is_enabled = False
    db.commit()
    return Response(status_code=204)


@router.get("/materials/{material_id}/imports", response_model=list[ImportOut])
def imports(material_id: uuid.UUID, db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(ImportSource)
            .where(ImportSource.material_id == material_id)
            .order_by(ImportSource.created_at)
        )
    )


@router.post(
    "/materials/{material_id}/imports",
    response_model=ImportOut,
    status_code=status.HTTP_201_CREATED,
)
def import_create(material_id: uuid.UUID, data: ImportCreate, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if material is None or material.archived_at is not None:
        raise HTTPException(404, "material not found")
    source = ImportSource(
        material_id=material.id,
        name=data.name,
        kind=data.kind,
        url=data.url,
        config=data.config,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    if data.sync_now:
        sync_import(db, source.id)
        db.refresh(source)
    return source


@router.patch("/imports/{import_id}", response_model=ImportOut)
def import_update(import_id: uuid.UUID, data: ImportUpdate, db: Session = Depends(get_db)):
    source = db.get(ImportSource, import_id)
    if source is None:
        raise HTTPException(404, "import source not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/imports/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
def import_delete(import_id: uuid.UUID, db: Session = Depends(get_db)):
    source = db.get(ImportSource, import_id)
    if source is None:
        raise HTTPException(404, "import source not found")
    db.delete(source)
    db.commit()
    return Response(status_code=204)


@router.post("/imports/{import_id}/sync", response_model=SyncResult)
def import_sync(import_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return sync_import(db, import_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/questions", response_model=list[QuestionOut])
def questions(
    q: str = "",
    material_ids: list[uuid.UUID] = Query(default=[]),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    learner = default_learner(db)
    return search_questions(db, learner.id, material_ids or None, q, limit)


@router.post("/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def question_create(data: QuestionCreate, db: Session = Depends(get_db)):
    try:
        question = create_question(db, data)
        if question is None:
            raise RuntimeError("question creation failed")
        return question_to_dict(question)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/questions/{question_id}", response_model=QuestionOut)
def question_update(question_id: uuid.UUID, data: QuestionUpdate, db: Session = Depends(get_db)):
    try:
        question = update_question(db, question_id, data)
        if question is None:
            raise RuntimeError("question update failed")
        return question_to_dict(question)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def question_archive(question_id: uuid.UUID, db: Session = Depends(get_db)):
    question = db.scalar(
        select(Question)
        .options(selectinload(Question.options), selectinload(Question.tags))
        .where(Question.id == question_id)
    )
    if question is None or question.archived_at is not None:
        raise HTTPException(404, "question not found")
    question.archived_at = utcnow()
    question.is_enabled = False
    db.commit()
    return Response(status_code=204)


@router.post("/study/sessions", response_model=StudySessionOut)
def study_session(data: StudySessionCreate, db: Session = Depends(get_db)):
    learner = default_learner(db)
    return create_study_session(db, learner, data.material_ids, data.limit, data.tags)


@router.post("/reviews", response_model=ReviewOut)
def review(data: ReviewCreate, db: Session = Depends(get_db)):
    learner = default_learner(db)
    try:
        state = submit_review(
            db,
            learner,
            data.question_id,
            data.rating,
            data.response_ms,
            data.mode,
            data.session_id,
            data.metadata,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return ReviewOut(
        mastery=state.mastery,
        due_at=state.due_at,
        stability=state.stability,
        difficulty=state.difficulty,
        reps=state.reps,
        lapses=state.lapses,
        streak=state.streak,
    )


@router.get("/stats/summary", response_model=StatsOut)
def stats_summary(db: Session = Depends(get_db)):
    learner = default_learner(db)
    return stats(db, learner)
