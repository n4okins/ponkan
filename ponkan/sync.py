import csv
import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request

from .db import connect, now

MAX_CSV_BYTES = int(os.environ.get("PONKAN_MAX_CSV_BYTES", str(10 * 1024 * 1024)))


def normalize_choices(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            value = json.loads(text)
            if isinstance(value, list):
                return [str(x).strip() for x in value if str(x).strip()]
        except json.JSONDecodeError:
            pass
    sep = "|" if "|" in text else ";"
    return [x.strip() for x in text.split(sep) if x.strip()]


def normalize_tags(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in re.split(r"[,|;]", str(value or "")) if x.strip()]


def boolish(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() not in {"0", "false", "off", "no", "disabled"}


def normalize_google_url(url):
    url = str(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname != "docs.google.com":
        return url
    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        return url
    query = urllib.parse.parse_qs(parsed.query)
    gid = (query.get("gid") or [None])[0]
    if gid is None and parsed.fragment.startswith("gid="):
        gid = parsed.fragment.split("=", 1)[1]
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={urllib.parse.quote(gid or '0')}"


def fetch_csv(url):
    url = normalize_google_url(url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("CSV URL must use http or https")
    request = urllib.request.Request(url, headers={"User-Agent": "Ponkan/2.0", "Accept": "text/csv,text/plain,*/*"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise ValueError("CSV is too large")
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def map_record(record, source):
    row = {str(k).strip().lower(): (v or "") for k, v in record.items() if k is not None}
    legacy = "word" in row or "meaning" in row
    prompt = (row.get("prompt") or row.get("question") or row.get("front") or row.get("word") or "").strip()
    answer = (row.get("answer") or row.get("back") or row.get("meaning") or "").strip()
    if not prompt or not answer:
        return None
    external_id = (row.get("id") or row.get("external_id") or "").strip()
    if not external_id:
        external_id = hashlib.sha256((prompt + "\0" + answer).encode()).hexdigest()[:20]
    explanation = (row.get("explanation") or row.get("note") or row.get("example") or "").strip()
    if legacy and row.get("example_ja"):
        explanation += (" / " if explanation else "") + row["example_ja"].strip()
    metadata = {}
    for key in ("pronunciation", "part_of_speech", "level", "example", "example_ja"):
        if row.get(key):
            metadata[key] = row[key].strip()
    return {
        "external_id": external_id,
        "prompt": prompt,
        "answer": answer,
        "choices": normalize_choices(row.get("choices") or row.get("distractors")),
        "explanation": explanation,
        "tags": normalize_tags(row.get("tags")),
        "prompt_lang": (row.get("prompt_lang") or source["default_prompt_lang"] or "").strip(),
        "answer_lang": (row.get("answer_lang") or source["default_answer_lang"] or "").strip(),
        "question_type": (row.get("question_type") or row.get("type") or "auto").strip(),
        "enabled": boolish(row.get("enabled")),
        "metadata": metadata,
    }


def sync_source(source_id):
    with connect() as db:
        source = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if not source:
            raise KeyError("source not found")
        if source["kind"] != "csv_url":
            raise ValueError("only csv_url sources can be synced")
        try:
            mapped = [q for q in (map_record(row, source) for row in fetch_csv(source["url"])) if q]
            if not mapped:
                raise ValueError("CSV contained no valid prompt/answer rows")
            t = now()
            external_ids = []
            for q in mapped:
                external_ids.append(q["external_id"])
                db.execute(
                    """INSERT INTO questions(source_id,external_id,prompt,answer,choices_json,explanation,tags_json,prompt_lang,answer_lang,question_type,enabled,metadata_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(source_id,external_id) DO UPDATE SET
                       prompt=excluded.prompt,answer=excluded.answer,choices_json=excluded.choices_json,
                       explanation=excluded.explanation,tags_json=excluded.tags_json,prompt_lang=excluded.prompt_lang,
                       answer_lang=excluded.answer_lang,question_type=excluded.question_type,enabled=excluded.enabled,
                       metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                    (source_id, q["external_id"], q["prompt"], q["answer"], json.dumps(q["choices"], ensure_ascii=False),
                     q["explanation"], json.dumps(q["tags"], ensure_ascii=False), q["prompt_lang"], q["answer_lang"],
                     q["question_type"], 1 if q["enabled"] else 0, json.dumps(q["metadata"], ensure_ascii=False), t, t),
                )
            placeholders = ",".join("?" for _ in external_ids)
            db.execute(f"DELETE FROM questions WHERE source_id=? AND external_id NOT IN ({placeholders})", [source_id, *external_ids])
            db.execute("UPDATE sources SET last_synced_at=?,sync_error=NULL,updated_at=? WHERE id=?", (t, t, source_id))
            return {"synced": len(mapped), "timestamp": t}
        except Exception as exc:
            db.execute("UPDATE sources SET sync_error=?,updated_at=? WHERE id=?", (str(exc), now(), source_id))
            raise
