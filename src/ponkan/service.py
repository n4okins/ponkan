from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Integer, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .importers import fetch_csv, parse_csv
from .models import (
    ImportSource,
    Learner,
    Material,
    Question,
    QuestionOption,
    ReviewEvent,
    ReviewState,
    StudySession,
    SyncRun,
    Tag,
    utcnow,
)
from .scheduler import ALGORITHM_VERSION, SchedulerState, recall_probability, schedule_review
from .schemas import QuestionCreate, QuestionUpdate

MASTER_WEIGHT = {"weak": 90, "fuzzy": 60, "almost": 30, "mastered": 5}


def default_learner(db: Session) -> Learner:
    learner = db.scalar(select(Learner).where(Learner.slug == "local"))
    if learner is None:
        learner = Learner(slug="local", name="Local learner")
        db.add(learner)
        db.flush()
    return learner


def seed_demo(db: Session) -> None:
    if (db.scalar(select(func.count(Material.id))) or 0) > 0:
        return
    default_learner(db)
    datasets = [
        (
            "English demo",
            "language",
            "en",
            "ja",
            [
                ("abandon", "捨てる・放棄する", "abandon a plan", ["english", "demo"]),
                ("achieve", "達成する", "achieve a goal", ["english", "demo"]),
                ("adequate", "十分な・適切な", "adequate preparation", ["english", "demo"]),
                ("ancient", "古代の", "ancient history", ["english", "demo"]),
            ],
        ),
        (
            "Русский demo",
            "language",
            "ru",
            "ja",
            [
                ("привет", "こんにちは", "基本的な挨拶", ["russian", "demo"]),
                ("спасибо", "ありがとう", "感謝を表す", ["russian", "demo"]),
                ("книга", "本", "名詞・女性名詞", ["russian", "demo"]),
                ("вода", "水", "名詞・女性名詞", ["russian", "demo"]),
            ],
        ),
        (
            "中文 demo",
            "language",
            "zh-CN",
            "ja",
            [
                ("你好", "こんにちは", "nǐ hǎo", ["chinese", "demo"]),
                ("谢谢", "ありがとう", "xièxie", ["chinese", "demo"]),
                ("学习", "学習する", "xuéxí", ["chinese", "demo"]),
                ("电脑", "コンピューター", "diànnǎo", ["chinese", "demo"]),
            ],
        ),
        (
            "セキスペ demo",
            "certification",
            "ja",
            "ja",
            [
                (
                    "CSRF対策として最も直接的なものはどれか",
                    "CSRFトークンを検証する",
                    "状態変更要求の正当性を検証する。",
                    ["security", "web"],
                ),
                (
                    "SQLインジェクション対策の基本はどれか",
                    "プレースホルダを用いたパラメータ化クエリ",
                    "入力をSQL構文へ直接連結しない。",
                    ["security", "sql"],
                ),
                (
                    "公開鍵暗号で秘密鍵を保持する主体は誰か",
                    "秘密鍵の所有者本人",
                    "公開鍵のみを相手に配布する。",
                    ["security", "crypto"],
                ),
                (
                    "可用性を主に損なう攻撃の代表例はどれか",
                    "DoS攻撃",
                    "DoS/DDoSはサービス資源を枯渇させる。",
                    ["security", "availability"],
                ),
            ],
        ),
    ]
    for name, category, prompt_lang, answer_lang, rows in datasets:
        material = Material(
            name=name,
            description="初期デモ。不要ならアーカイブできます。",
            category=category,
            default_prompt_lang=prompt_lang,
            default_answer_lang=answer_lang,
        )
        db.add(material)
        db.flush()
        for prompt, answer, explanation, tags in rows:
            question = Question(
                material_id=material.id,
                prompt=prompt,
                answer=answer,
                explanation=explanation,
                prompt_lang=prompt_lang,
                answer_lang=answer_lang,
                question_type="auto",
            )
            db.add(question)
            db.flush()
            set_tags(db, question, tags)
    db.commit()


def list_materials(db: Session, learner_id: uuid.UUID) -> list[dict]:
    at = utcnow()
    question_count = (
        select(func.count(Question.id))
        .where(
            Question.material_id == Material.id,
            Question.archived_at.is_(None),
            Question.is_enabled.is_(True),
        )
        .correlate(Material)
        .scalar_subquery()
    )
    due_count = (
        select(func.count(ReviewState.question_id))
        .join(Question, Question.id == ReviewState.question_id)
        .where(
            Question.material_id == Material.id,
            ReviewState.learner_id == learner_id,
            ReviewState.due_at <= at,
            Question.archived_at.is_(None),
            Question.is_enabled.is_(True),
        )
        .correlate(Material)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Material, question_count.label("question_count"), due_count.label("due_count"))
        .where(Material.archived_at.is_(None))
        .order_by(Material.name)
    ).all()
    return [
        {
            "id": material.id,
            "name": material.name,
            "description": material.description,
            "category": material.category,
            "default_prompt_lang": material.default_prompt_lang,
            "default_answer_lang": material.default_answer_lang,
            "is_enabled": material.is_enabled,
            "archived_at": material.archived_at,
            "question_count": count or 0,
            "due_count": due or 0,
        }
        for material, count, due in rows
    ]


def set_tags(db: Session, question: Question, names: list[str]) -> None:
    cleaned = sorted({item.strip().lower() for item in names if item.strip()})
    tags: list[Tag] = []
    for name in cleaned:
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    question.tags = tags


def set_options(db: Session, question: Question, choices: list[str], answer: str) -> None:
    question.options.clear()
    values: list[str] = []
    for raw in [answer, *choices]:
        text = raw.strip()
        if text and text not in values:
            values.append(text)
    if len(values) < 2:
        return
    for position, text in enumerate(values):
        question.options.append(
            QuestionOption(text=text, is_correct=text == answer, position=position)
        )


def create_question(db: Session, data: QuestionCreate) -> Question:
    material = db.get(Material, data.material_id)
    if material is None or material.archived_at is not None:
        raise KeyError("material not found")
    question = Question(
        material_id=material.id,
        prompt=data.prompt.strip(),
        answer=data.answer.strip(),
        explanation=data.explanation,
        question_type=data.question_type,
        prompt_lang=data.prompt_lang or material.default_prompt_lang,
        answer_lang=data.answer_lang or material.default_answer_lang,
        metadata_json=data.metadata,
        is_enabled=data.is_enabled,
    )
    db.add(question)
    db.flush()
    set_tags(db, question, data.tags)
    set_options(db, question, data.choices, question.answer)
    db.commit()
    return db.scalar(
        select(Question)
        .options(selectinload(Question.options), selectinload(Question.tags))
        .where(Question.id == question.id)
    )


def update_question(db: Session, question_id: uuid.UUID, data: QuestionUpdate) -> Question:
    question = db.scalar(
        select(Question)
        .options(selectinload(Question.options), selectinload(Question.tags))
        .where(Question.id == question_id)
    )
    if question is None or question.archived_at is not None:
        raise KeyError("question not found")
    patch = data.model_dump(exclude_unset=True)
    if "prompt" in patch:
        question.prompt = patch["prompt"].strip()
    if "answer" in patch:
        question.answer = patch["answer"].strip()
    for field in ("explanation", "question_type", "prompt_lang", "answer_lang", "is_enabled"):
        if field in patch:
            setattr(question, field, patch[field])
    if "metadata" in patch:
        question.metadata_json = patch["metadata"]
    if "tags" in patch:
        set_tags(db, question, patch["tags"])
    if "choices" in patch or "answer" in patch:
        existing = patch.get(
            "choices",
            [option.text for option in question.options if not option.is_correct],
        )
        set_options(db, question, existing, question.answer)
    db.commit()
    return db.scalar(
        select(Question)
        .options(selectinload(Question.options), selectinload(Question.tags))
        .where(Question.id == question.id)
    )


def question_to_dict(
    question: Question,
    state: ReviewState | None = None,
    generated_choices: list[str] | None = None,
) -> dict:
    choices = generated_choices if generated_choices is not None else [x.text for x in question.options]
    return {
        "id": question.id,
        "material_id": question.material_id,
        "import_source_id": question.import_source_id,
        "external_key": question.external_key,
        "prompt": question.prompt,
        "answer": question.answer,
        "explanation": question.explanation,
        "question_type": question.question_type,
        "prompt_lang": question.prompt_lang,
        "answer_lang": question.answer_lang,
        "metadata": question.metadata_json,
        "is_enabled": question.is_enabled,
        "archived_at": question.archived_at,
        "choices": choices,
        "tags": [tag.name for tag in question.tags],
        "mastery": state.mastery if state else None,
        "due_at": state.due_at if state else None,
    }


def search_questions(
    db: Session,
    learner_id: uuid.UUID,
    material_ids: list[uuid.UUID] | None = None,
    query: str = "",
    limit: int = 200,
) -> list[dict]:
    stmt = (
        select(Question, ReviewState)
        .outerjoin(
            ReviewState,
            and_(ReviewState.question_id == Question.id, ReviewState.learner_id == learner_id),
        )
        .options(selectinload(Question.options), selectinload(Question.tags))
        .join(Material, Material.id == Question.material_id)
        .where(
            Question.archived_at.is_(None),
            Question.is_enabled.is_(True),
            Material.archived_at.is_(None),
            Material.is_enabled.is_(True),
        )
    )
    if material_ids:
        stmt = stmt.where(Question.material_id.in_(material_ids))
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                Question.prompt.ilike(like),
                Question.answer.ilike(like),
                Question.explanation.ilike(like),
            )
        )
    stmt = stmt.order_by(Question.updated_at.desc()).limit(min(limit, 1000))
    return [question_to_dict(question, state) for question, state in db.execute(stmt).unique().all()]


def _priority(state: ReviewState | None, at: datetime) -> float:
    if state is None:
        return 160 + random.random() * 10
    scheduler_state = SchedulerState(
        due_at=state.due_at,
        stability=state.stability,
        difficulty=state.difficulty,
        reps=state.reps,
        lapses=state.lapses,
        streak=state.streak,
        last_rating=state.last_rating,
        last_reviewed_at=state.last_reviewed_at,
        avg_response_ms=state.avg_response_ms,
        mastery=state.mastery,
    )
    recall = recall_probability(scheduler_state, at)
    overdue = max(0.0, (at - state.due_at).total_seconds() / 86400)
    return (
        MASTER_WEIGHT.get(state.mastery, 40)
        + min(100, overdue * 5)
        + (1 - recall) * 50
        + random.random() * 6
    )


def create_study_session(
    db: Session,
    learner: Learner,
    material_ids: list[uuid.UUID],
    limit: int,
    tags: list[str] | None = None,
) -> dict:
    at = utcnow()
    stmt = (
        select(Question, ReviewState)
        .outerjoin(
            ReviewState,
            and_(ReviewState.question_id == Question.id, ReviewState.learner_id == learner.id),
        )
        .options(selectinload(Question.options), selectinload(Question.tags))
        .join(Material, Material.id == Question.material_id)
        .where(
            Question.material_id.in_(material_ids),
            Question.is_enabled.is_(True),
            Question.archived_at.is_(None),
            Material.is_enabled.is_(True),
            Material.archived_at.is_(None),
        )
    )
    rows = db.execute(stmt).unique().all()
    if tags:
        required = {item.lower() for item in tags}
        rows = [
            (question, state)
            for question, state in rows
            if required.intersection({tag.name for tag in question.tags})
        ]
    scored = sorted(
        ((_priority(state, at), question, state) for question, state in rows),
        key=lambda item: item[0],
        reverse=True,
    )
    chosen = scored[: max(1, min(limit, 100))]
    session = StudySession(
        learner_id=learner.id,
        settings={"material_ids": [str(x) for x in material_ids], "limit": limit, "tags": tags or []},
    )
    db.add(session)
    db.flush()

    answer_pool: dict[uuid.UUID, list[str]] = {}
    for question, _state in rows:
        answer_pool.setdefault(question.material_id, []).append(question.answer)

    result: list[dict] = []
    for _score, question, state in chosen:
        explicit = [option.text for option in question.options]
        if question.question_type == "card":
            choices: list[str] = []
        elif len(explicit) >= 2:
            choices = explicit[:]
            random.shuffle(choices)
        else:
            candidates = list(
                dict.fromkeys(
                    answer
                    for answer in answer_pool.get(question.material_id, [])
                    if answer != question.answer
                )
            )
            random.shuffle(candidates)
            choices = [question.answer, *candidates[:3]] if candidates else []
            random.shuffle(choices)
        result.append(
            {
                "id": question.id,
                "material_id": question.material_id,
                "prompt": question.prompt,
                "answer": question.answer,
                "explanation": question.explanation,
                "question_type": question.question_type,
                "prompt_lang": question.prompt_lang,
                "answer_lang": question.answer_lang,
                "choices": choices,
                "tags": [tag.name for tag in question.tags],
                "mastery": state.mastery if state else "weak",
                "due_at": state.due_at if state else None,
            }
        )
    db.commit()
    return {"session_id": session.id, "total_pool": len(rows), "questions": result}


def submit_review(
    db: Session,
    learner: Learner,
    question_id: uuid.UUID,
    rating: int,
    response_ms: int,
    mode: str,
    session_id: uuid.UUID | None,
    metadata: dict,
) -> ReviewState:
    question = db.get(Question, question_id)
    if question is None or question.archived_at is not None:
        raise KeyError("question not found")
    state = db.get(ReviewState, (learner.id, question_id))
    at = utcnow()
    if state is None:
        state = ReviewState(learner_id=learner.id, question_id=question_id, due_at=at)
        db.add(state)
        db.flush()
    before = SchedulerState(
        due_at=state.due_at,
        stability=state.stability,
        difficulty=state.difficulty,
        reps=state.reps,
        lapses=state.lapses,
        streak=state.streak,
        last_rating=state.last_rating,
        last_reviewed_at=state.last_reviewed_at,
        avg_response_ms=state.avg_response_ms,
        mastery=state.mastery,
    )
    after, scheduled_days = schedule_review(before, rating, response_ms, at)
    state.algorithm_version = ALGORITHM_VERSION
    state.due_at = after.due_at
    state.stability = after.stability
    state.difficulty = after.difficulty
    state.reps = after.reps
    state.lapses = after.lapses
    state.streak = after.streak
    state.last_rating = after.last_rating
    state.last_reviewed_at = after.last_reviewed_at
    state.avg_response_ms = after.avg_response_ms
    state.mastery = after.mastery
    db.add(
        ReviewEvent(
            learner_id=learner.id,
            question_id=question_id,
            session_id=session_id,
            reviewed_at=at,
            rating=rating,
            is_correct=rating > 1,
            response_ms=response_ms,
            mode=mode,
            scheduled_days=scheduled_days,
            stability_before=before.stability,
            stability_after=after.stability,
            difficulty_before=before.difficulty,
            difficulty_after=after.difficulty,
            metadata_json=metadata,
        )
    )
    db.commit()
    db.refresh(state)
    return state


def stats(db: Session, learner: Learner) -> dict:
    at = utcnow()
    day_ago = at - timedelta(days=1)
    active_questions = db.scalar(
        select(func.count(Question.id))
        .join(Material, Material.id == Question.material_id)
        .where(
            Question.is_enabled.is_(True),
            Question.archived_at.is_(None),
            Material.archived_at.is_(None),
            Material.is_enabled.is_(True),
        )
    ) or 0
    learned = db.scalar(
        select(func.count(ReviewState.question_id))
        .join(Question, Question.id == ReviewState.question_id)
        .join(Material, Material.id == Question.material_id)
        .where(
            ReviewState.learner_id == learner.id,
            ReviewState.reps > 0,
            Question.archived_at.is_(None),
            Material.archived_at.is_(None),
            Material.is_enabled.is_(True),
        )
    ) or 0
    due = db.scalar(
        select(func.count(ReviewState.question_id))
        .join(Question, Question.id == ReviewState.question_id)
        .join(Material, Material.id == Question.material_id)
        .where(
            ReviewState.learner_id == learner.id,
            ReviewState.due_at <= at,
            Question.is_enabled.is_(True),
            Question.archived_at.is_(None),
            Material.archived_at.is_(None),
            Material.is_enabled.is_(True),
        )
    ) or 0
    reviews, correct = db.execute(
        select(func.count(ReviewEvent.id), func.sum(func.cast(ReviewEvent.is_correct, Integer))).where(
            ReviewEvent.learner_id == learner.id,
            ReviewEvent.reviewed_at >= day_ago,
        )
    ).one()
    mastery_rows = db.execute(
        select(ReviewState.mastery, func.count())
        .join(Question, Question.id == ReviewState.question_id)
        .join(Material, Material.id == Question.material_id)
        .where(
            ReviewState.learner_id == learner.id,
            Question.archived_at.is_(None),
            Material.archived_at.is_(None),
            Material.is_enabled.is_(True),
        )
        .group_by(ReviewState.mastery)
    ).all()
    return {
        "active_questions": active_questions,
        "learned_questions": learned,
        "due_questions": due,
        "reviews_24h": reviews or 0,
        "accuracy_24h": (float(correct or 0) / reviews) if reviews else 0.0,
        "mastery": {name: count for name, count in mastery_rows},
    }


def sync_import(db: Session, import_source_id: uuid.UUID) -> dict:
    source = db.get(ImportSource, import_source_id)
    if source is None:
        raise KeyError("import source not found")
    material = db.get(Material, source.material_id)
    if material is None:
        raise KeyError("material not found")

    run = SyncRun(import_source_id=source.id)
    db.add(run)
    source.last_sync_status = "running"
    source.last_sync_error = ""
    db.commit()
    db.refresh(run)

    try:
        text = fetch_csv(source.url)
        items = parse_csv(text, material.default_prompt_lang, material.default_answer_lang)
        seen_keys = {item.external_key for item in items}
        created = 0
        updated = 0
        existing = {
            question.external_key: question
            for question in db.scalars(
                select(Question)
                .options(selectinload(Question.options), selectinload(Question.tags))
                .where(Question.import_source_id == source.id)
            ).unique()
            if question.external_key is not None
        }
        for item in items:
            question = existing.get(item.external_key)
            if question is None:
                question = Question(
                    material_id=material.id,
                    import_source_id=source.id,
                    external_key=item.external_key,
                    prompt=item.prompt,
                    answer=item.answer,
                    explanation=item.explanation,
                    question_type=item.question_type,
                    prompt_lang=item.prompt_lang,
                    answer_lang=item.answer_lang,
                    content_hash=item.content_hash,
                    metadata_json=item.metadata,
                )
                db.add(question)
                db.flush()
                set_options(db, question, item.choices, item.answer)
                set_tags(db, question, item.tags)
                created += 1
            elif question.content_hash != item.content_hash or question.archived_at is not None:
                question.prompt = item.prompt
                question.answer = item.answer
                question.explanation = item.explanation
                question.question_type = item.question_type
                question.prompt_lang = item.prompt_lang
                question.answer_lang = item.answer_lang
                question.content_hash = item.content_hash
                question.metadata_json = item.metadata
                question.archived_at = None
                question.is_enabled = True
                set_options(db, question, item.choices, item.answer)
                set_tags(db, question, item.tags)
                updated += 1

        archived = 0
        for key, question in existing.items():
            if key not in seen_keys and question.archived_at is None:
                question.archived_at = utcnow()
                archived += 1

        source.last_synced_at = utcnow()
        source.last_sync_status = "ok"
        run.finished_at = utcnow()
        run.status = "ok"
        run.seen_count = len(items)
        run.created_count = created
        run.updated_count = updated
        run.archived_count = archived
        db.commit()
        return {
            "run_id": run.id,
            "status": "ok",
            "seen": len(items),
            "created": created,
            "updated": updated,
            "archived": archived,
            "error": "",
        }
    except Exception as exc:
        db.rollback()
        source = db.get(ImportSource, import_source_id)
        run = db.get(SyncRun, run.id)
        if source is None or run is None:
            raise
        source.last_sync_status = "error"
        source.last_sync_error = str(exc)
        source.last_synced_at = utcnow()
        run.finished_at = utcnow()
        run.status = "error"
        run.error = str(exc)
        db.commit()
        return {
            "run_id": run.id,
            "status": "error",
            "seen": 0,
            "created": 0,
            "updated": 0,
            "archived": 0,
            "error": str(exc),
        }
