from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

ALGORITHM_VERSION = "ponkan-srs-v1"


@dataclass(slots=True)
class SchedulerState:
    due_at: datetime
    stability: float = 0.5
    difficulty: float = 5.0
    reps: int = 0
    lapses: int = 0
    streak: int = 0
    last_rating: int | None = None
    last_reviewed_at: datetime | None = None
    avg_response_ms: float = 0.0
    mastery: str = "weak"


def recall_probability(state: SchedulerState, at: datetime) -> float:
    if state.last_reviewed_at is None:
        return 0.0
    elapsed = max(0.0, (at - state.last_reviewed_at).total_seconds() / 86400)
    return 0.9 ** (elapsed / max(0.25, state.stability))


def mastery_for(stability: float, reps: int, lapses: int, streak: int, rating: int) -> str:
    if rating == 1 or stability < 1:
        return "weak"
    if stability < 4:
        return "fuzzy"
    if stability < 14:
        return "almost"
    return "mastered" if reps >= 3 and streak >= 2 and reps > lapses else "almost"


def schedule_review(
    state: SchedulerState,
    rating: int,
    response_ms: int,
    reviewed_at: datetime | None = None,
) -> tuple[SchedulerState, float]:
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1..4")
    at = reviewed_at or datetime.now(UTC)
    recall = recall_probability(state, at)
    old_stability = state.stability

    reps = state.reps + 1
    lapses = state.lapses + (1 if rating == 1 else 0)
    streak = 0 if rating == 1 else state.streak + 1

    if rating == 1:
        stability = max(0.25, old_stability * 0.35)
        difficulty = min(10.0, state.difficulty + 0.8)
    elif rating == 2:
        growth = 1.25 + 0.35 * (1 - recall)
        stability = max(0.75, old_stability * growth)
        difficulty = min(10.0, state.difficulty + 0.15)
    elif rating == 3:
        growth = 2.0 + 1.2 * (1 - recall)
        stability = max(1.0 if state.reps == 0 else old_stability, old_stability * growth)
        difficulty = max(1.0, state.difficulty - 0.2)
    else:
        growth = 3.0 + 1.5 * (1 - recall)
        stability = max(3.0 if state.reps == 0 else old_stability, old_stability * growth)
        difficulty = max(1.0, state.difficulty - 0.45)

    if rating >= 3 and response_ms > 8000:
        stability *= 0.8

    scheduled_days = max(0.25, stability)
    avg = response_ms if state.reps == 0 else state.avg_response_ms * 0.8 + response_ms * 0.2
    mastery = mastery_for(stability, reps, lapses, streak, rating)

    return (
        SchedulerState(
            due_at=at + timedelta(days=scheduled_days),
            stability=stability,
            difficulty=difficulty,
            reps=reps,
            lapses=lapses,
            streak=streak,
            last_rating=rating,
            last_reviewed_at=at,
            avg_response_ms=avg,
            mastery=mastery,
        ),
        scheduled_days,
    )
