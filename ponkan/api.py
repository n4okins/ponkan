import json
import random
import re
import sqlite3
import urllib.parse
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

from .db import connect, now, question_dict, source_dict
from .study import make_session, record_review
from .sync import normalize_choices, normalize_tags, sync_source

PUBLIC = Path(__file__).resolve().parent.parent / "public"


class Handler(SimpleHTTPRequestHandler):
    server_version = "Ponkan/2.0"

    def translate_path(self, path):
        rel = urllib.parse.urlparse(path).path.lstrip("/") or "index.html"
        target = (PUBLIC / rel).resolve()
        try:
            target.relative_to(PUBLIC.resolve())
        except ValueError:
            return str(PUBLIC / "404")
        return str(target)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")

    def json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def input_json(self):
        size = int(self.headers.get("Content-Length", "0") or 0)
        if size > 2 * 1024 * 1024:
            raise ValueError("request too large")
        return json.loads((self.rfile.read(size) if size else b"{}").decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        try:
            if parsed.path == "/api/health":
                return self.json({"ok": True, "version": "2.0.0"})
            if parsed.path == "/api/sources":
                with connect() as db:
                    rows = db.execute(
                        "SELECT s.*,COUNT(q.id) question_count FROM sources s LEFT JOIN questions q ON q.source_id=s.id GROUP BY s.id ORDER BY s.id"
                    ).fetchall()
                    return self.json([source_dict(r) for r in rows])
            if parsed.path == "/api/questions":
                params = urllib.parse.parse_qs(parsed.query)
                source_ids = [int(x) for x in params.get("source_ids", [""])[0].split(",") if x.isdigit()]
                query = params.get("q", [""])[0].strip()
                sql, args = "SELECT q.* FROM questions q WHERE 1=1", []
                if source_ids:
                    sql += " AND q.source_id IN (%s)" % ",".join("?" for _ in source_ids)
                    args.extend(source_ids)
                if query:
                    sql += " AND (q.prompt LIKE ? OR q.answer LIKE ? OR q.explanation LIKE ?)"
                    like = f"%{query}%"
                    args.extend([like, like, like])
                sql += " ORDER BY q.source_id,q.id LIMIT 2000"
                with connect() as db:
                    return self.json([question_dict(r) for r in db.execute(sql, args).fetchall()])
            if parsed.path == "/api/study/session":
                params = urllib.parse.parse_qs(parsed.query)
                ids = [int(x) for x in params.get("source_ids", [""])[0].split(",") if x.isdigit()]
                limit = int(params.get("limit", ["20"])[0])
                return self.json(make_session(ids, limit))
            if parsed.path == "/api/stats":
                with connect() as db:
                    total = db.execute("SELECT COUNT(*) FROM questions WHERE enabled=1").fetchone()[0]
                    learned = db.execute("SELECT COUNT(*) FROM progress WHERE seen>0").fetchone()[0]
                    r = db.execute("SELECT COUNT(*) n,COALESCE(SUM(correct),0) c FROM reviews WHERE reviewed_at>=?", (now() - 86400,)).fetchone()
                    levels = {x["mastery"]: x["n"] for x in db.execute("SELECT mastery,COUNT(*) n FROM progress GROUP BY mastery")}
                    return self.json({"questions": total, "learned": learned, "reviews_24h": r["n"], "correct_24h": r["c"], "mastery": levels})
            return self.json({"error": "not found"}, 404)
        except Exception as exc:
            return self.json({"error": str(exc)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            data = self.input_json()
            if parsed.path == "/api/sources":
                name = str(data.get("name", "")).strip()
                kind = str(data.get("kind", "manual"))
                if not name:
                    return self.json({"error": "name is required"}, 400)
                if kind not in {"manual", "csv_url"}:
                    return self.json({"error": "invalid kind"}, 400)
                t = now()
                with connect() as db:
                    cur = db.execute(
                        """INSERT INTO sources(name,description,kind,url,category,default_prompt_lang,default_answer_lang,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (name, str(data.get("description", "")), kind, str(data.get("url", "")),
                         str(data.get("category", "general")), str(data.get("default_prompt_lang", "")),
                         str(data.get("default_answer_lang", "")), t, t),
                    )
                    source_id = cur.lastrowid
                result = sync_source(source_id) if kind == "csv_url" and data.get("sync_now", True) else None
                return self.json({"id": source_id, "sync": result}, 201)
            match = re.fullmatch(r"/api/sources/(\d+)/sync", parsed.path)
            if match:
                return self.json(sync_source(int(match.group(1))))
            if parsed.path == "/api/questions":
                source_id = int(data.get("source_id", 0))
                prompt, answer = str(data.get("prompt", "")).strip(), str(data.get("answer", "")).strip()
                if not source_id or not prompt or not answer:
                    return self.json({"error": "source_id, prompt and answer are required"}, 400)
                with connect() as db:
                    source = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
                    if not source:
                        return self.json({"error": "source not found"}, 404)
                    t = now()
                    external_id = str(data.get("external_id") or f"manual-{int(t * 1000)}-{random.randint(100,999)}")
                    cur = db.execute(
                        """INSERT INTO questions(source_id,external_id,prompt,answer,choices_json,explanation,tags_json,prompt_lang,answer_lang,question_type,enabled,metadata_json,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (source_id, external_id, prompt, answer, json.dumps(normalize_choices(data.get("choices")), ensure_ascii=False),
                         str(data.get("explanation", "")), json.dumps(normalize_tags(data.get("tags")), ensure_ascii=False),
                         str(data.get("prompt_lang") or source["default_prompt_lang"]), str(data.get("answer_lang") or source["default_answer_lang"]),
                         str(data.get("question_type", "auto")), 1, "{}", t, t),
                    )
                    return self.json({"id": cur.lastrowid}, 201)
            if parsed.path == "/api/reviews":
                question_id = int(data.get("question_id", 0))
                response_ms = max(0, min(300000, int(data.get("response_ms", 0) or 0)))
                return self.json(record_review(question_id, bool(data.get("correct")), response_ms, str(data.get("mode", "choice"))))
            return self.json({"error": "not found"}, 404)
        except sqlite3.IntegrityError as exc:
            return self.json({"error": str(exc)}, 409)
        except KeyError as exc:
            return self.json({"error": str(exc)}, 404)
        except Exception as exc:
            return self.json({"error": str(exc)}, 500)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            data = self.input_json()
            match = re.fullmatch(r"/api/sources/(\d+)", parsed.path)
            if match:
                source_id = int(match.group(1))
                with connect() as db:
                    old = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
                    if not old:
                        return self.json({"error": "source not found"}, 404)
                    values = {k: data.get(k, old[k]) for k in ("name", "description", "kind", "url", "category", "default_prompt_lang", "default_answer_lang")}
                    if values["kind"] not in {"manual", "csv_url"}:
                        return self.json({"error": "invalid kind"}, 400)
                    db.execute(
                        """UPDATE sources SET name=?,description=?,kind=?,url=?,category=?,default_prompt_lang=?,default_answer_lang=?,updated_at=? WHERE id=?""",
                        (values["name"], values["description"], values["kind"], values["url"], values["category"],
                         values["default_prompt_lang"], values["default_answer_lang"], now(), source_id),
                    )
                return self.json({"ok": True})
            match = re.fullmatch(r"/api/questions/(\d+)", parsed.path)
            if match:
                question_id = int(match.group(1))
                with connect() as db:
                    old = db.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
                    if not old:
                        return self.json({"error": "question not found"}, 404)
                    choices = normalize_choices(data.get("choices", json.loads(old["choices_json"])))
                    tags = normalize_tags(data.get("tags", json.loads(old["tags_json"])))
                    db.execute(
                        """UPDATE questions SET prompt=?,answer=?,choices_json=?,explanation=?,tags_json=?,prompt_lang=?,answer_lang=?,question_type=?,enabled=?,updated_at=? WHERE id=?""",
                        (data.get("prompt", old["prompt"]), data.get("answer", old["answer"]), json.dumps(choices, ensure_ascii=False),
                         data.get("explanation", old["explanation"]), json.dumps(tags, ensure_ascii=False), data.get("prompt_lang", old["prompt_lang"]),
                         data.get("answer_lang", old["answer_lang"]), data.get("question_type", old["question_type"]),
                         1 if data.get("enabled", bool(old["enabled"])) else 0, now(), question_id),
                    )
                return self.json({"ok": True})
            return self.json({"error": "not found"}, 404)
        except Exception as exc:
            return self.json({"error": str(exc)}, 500)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/sources/(\d+)", parsed.path)
            table = "sources" if match else None
            if not match:
                match = re.fullmatch(r"/api/questions/(\d+)", parsed.path)
                table = "questions" if match else None
            if not match:
                return self.json({"error": "not found"}, 404)
            with connect() as db:
                cur = db.execute(f"DELETE FROM {table} WHERE id=?", (int(match.group(1)),))
                if cur.rowcount == 0:
                    return self.json({"error": f"{table[:-1]} not found"}, 404)
            return self.json({"ok": True})
        except Exception as exc:
            return self.json({"error": str(exc)}, 500)
