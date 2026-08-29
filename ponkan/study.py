import random

from .db import connect, now, question_dict


def mastery(stability, correct, wrong, streak, last_result):
    if last_result == "wrong" or stability < 1:
        return "weak"
    if stability < 4:
        return "fuzzy"
    if stability < 14:
        return "almost"
    return "mastered" if correct >= wrong and streak >= 2 else "almost"


def record_review(question_id, is_correct, response_ms=0, mode="choice"):
    t = now()
    with connect() as db:
        if not db.execute("SELECT 1 FROM questions WHERE id=?", (question_id,)).fetchone():
            raise KeyError("question not found")
        row = db.execute("SELECT * FROM progress WHERE question_id=?", (question_id,)).fetchone()
        if not row:
            db.execute("INSERT INTO progress(question_id) VALUES(?)", (question_id,))
            row = db.execute("SELECT * FROM progress WHERE question_id=?", (question_id,)).fetchone()

        seen = row["seen"] + 1
        correct = row["correct"] + int(is_correct)
        wrong = row["wrong"] + int(not is_correct)
        streak = row["correct_streak"] + 1 if is_correct else 0
        stability = float(row["stability"])
        difficulty = float(row["difficulty"])

        if is_correct:
            factor = 3.0 if 0 < response_ms < 1500 else 2.2 if response_ms < 4000 else 1.35
            stability = max(1.0 if seen == 1 else 0.7, stability * factor)
            difficulty = max(1.0, difficulty - (0.35 if factor >= 2.2 else 0.1))
            result = "correct"
        else:
            stability = max(0.25, stability * 0.25)
            difficulty = min(10.0, difficulty + 0.8)
            result = "wrong"

        due_at = t + stability * 86400
        avg = response_ms if row["avg_response_ms"] <= 0 else row["avg_response_ms"] * 0.8 + response_ms * 0.2
        level = mastery(stability, correct, wrong, streak, result)
        db.execute(
            """UPDATE progress SET seen=?,correct=?,wrong=?,correct_streak=?,stability=?,difficulty=?,due_at=?,
               last_reviewed_at=?,last_result=?,avg_response_ms=?,mastery=? WHERE question_id=?""",
            (seen, correct, wrong, streak, stability, difficulty, due_at, t, result, avg, level, question_id),
        )
        db.execute(
            "INSERT INTO reviews(question_id,reviewed_at,correct,response_ms,mode) VALUES(?,?,?,?,?)",
            (question_id, t, int(is_correct), response_ms, mode),
        )
        return dict(db.execute("SELECT * FROM progress WHERE question_id=?", (question_id,)).fetchone())


def priority(progress, t):
    if progress is None:
        return 160 + random.random() * 15
    weights = {"weak": 90, "fuzzy": 65, "almost": 35, "mastered": 5}
    overdue = max(0, (t - progress["due_at"]) / 86400) if progress["due_at"] else 0
    if progress["last_reviewed_at"]:
        elapsed = max(0, (t - progress["last_reviewed_at"]) / 86400)
        recall = 0.9 ** (elapsed / max(0.25, progress["stability"]))
    else:
        recall = 0
    return weights.get(progress["mastery"], 50) + min(80, overdue * 4) + (1 - recall) * 55 + random.random() * 8


def _generated_choices(question, pool):
    """Generate plausible distractors without crossing domains unless necessary."""
    answer = question["answer"]

    same_source = [
        item["answer"] for item in pool
        if item["source_id"] == question["source_id"] and item["answer"] != answer
    ]
    same_answer_lang = [
        item["answer"] for item in pool
        if item["answer_lang"] == question["answer_lang"] and item["answer"] != answer
    ]
    fallback = [item["answer"] for item in pool if item["answer"] != answer]

    candidates = list(dict.fromkeys([*same_source, *same_answer_lang, *fallback]))
    if len(candidates) < 1:
        return []
    random.shuffle(candidates)
    choices = [answer, *candidates[:3]]
    random.shuffle(choices)
    return choices


def make_session(source_ids, limit=20):
    if not source_ids:
        raise ValueError("select at least one source")
    limit = max(1, min(100, int(limit)))
    placeholders = ",".join("?" for _ in source_ids)
    with connect() as db:
        rows = db.execute(
            f"""SELECT q.*,p.seen,p.correct,p.wrong,p.correct_streak,p.stability,p.difficulty,p.due_at,
                       p.last_reviewed_at,p.last_result,p.avg_response_ms,p.mastery
                FROM questions q LEFT JOIN progress p ON p.question_id=q.id
                WHERE q.enabled=1 AND q.source_id IN ({placeholders})""",
            source_ids,
        ).fetchall()
        t = now()
        scored = []
        pool = []
        for row in rows:
            q = question_dict(row)
            pool.append(q.copy())
            progress = None if row["seen"] is None else row
            q["progress"] = None if progress is None else {k: row[k] for k in (
                "seen", "correct", "wrong", "correct_streak", "stability", "difficulty", "due_at",
                "last_reviewed_at", "last_result", "avg_response_ms", "mastery")}
            scored.append((priority(progress, t), q))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [q for _, q in scored[:limit]]
        for q in selected:
            if q["question_type"] != "card" and len(q["choices"]) < 2:
                q["choices"] = _generated_choices(q, pool)
        return {"questions": selected, "total_pool": len(rows)}
