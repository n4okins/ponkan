from datetime import UTC, datetime

from ponkan.scheduler import SchedulerState, recall_probability, schedule_review


def state() -> SchedulerState:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    return SchedulerState(due_at=now, last_reviewed_at=None)


def test_good_increases_stability_and_schedules_future():
    before = state()
    after, days = schedule_review(before, 3, 1800, datetime(2026, 8, 29, tzinfo=UTC))
    assert after.stability >= 1.0
    assert days == after.stability
    assert after.reps == 1
    assert after.streak == 1


def test_again_counts_lapse_and_resets_streak():
    before = state()
    before.reps = 4
    before.streak = 3
    before.stability = 10
    after, _ = schedule_review(before, 1, 5000, datetime(2026, 8, 29, tzinfo=UTC))
    assert after.lapses == 1
    assert after.streak == 0
    assert after.stability < before.stability
    assert after.mastery == "weak"


def test_recall_probability_at_stability_is_point_nine():
    start = datetime(2026, 8, 1, tzinfo=UTC)
    scheduler_state = SchedulerState(due_at=start, stability=10, last_reviewed_at=start)
    later = datetime(2026, 8, 11, tzinfo=UTC)
    assert abs(recall_probability(scheduler_state, later) - 0.9) < 1e-9
