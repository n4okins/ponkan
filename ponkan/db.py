import json
import os
import sqlite3
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("PONKAN_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "ponkan.db"


def now():
    return time.time()


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def init_db():
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL DEFAULT 'manual',
              url TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL DEFAULT 'general',
              default_prompt_lang TEXT NOT NULL DEFAULT '',
              default_answer_lang TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              last_synced_at REAL,
              sync_error TEXT
            );

            CREATE TABLE IF NOT EXISTS questions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
              external_id TEXT NOT NULL,
              prompt TEXT NOT NULL,
              answer TEXT NOT NULL,
              choices_json TEXT NOT NULL DEFAULT '[]',
              explanation TEXT NOT NULL DEFAULT '',
              tags_json TEXT NOT NULL DEFAULT '[]',
              prompt_lang TEXT NOT NULL DEFAULT '',
              answer_lang TEXT NOT NULL DEFAULT '',
              question_type TEXT NOT NULL DEFAULT 'auto',
              enabled INTEGER NOT NULL DEFAULT 1,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              UNIQUE(source_id, external_id)
            );

            CREATE TABLE IF NOT EXISTS progress (
              question_id INTEGER PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
              seen INTEGER NOT NULL DEFAULT 0,
              correct INTEGER NOT NULL DEFAULT 0,
              wrong INTEGER NOT NULL DEFAULT 0,
              correct_streak INTEGER NOT NULL DEFAULT 0,
              stability REAL NOT NULL DEFAULT 0.5,
              difficulty REAL NOT NULL DEFAULT 5.0,
              due_at REAL NOT NULL DEFAULT 0,
              last_reviewed_at REAL,
              last_result TEXT,
              avg_response_ms REAL NOT NULL DEFAULT 0,
              mastery TEXT NOT NULL DEFAULT 'weak'
            );

            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
              reviewed_at REAL NOT NULL,
              correct INTEGER NOT NULL,
              response_ms INTEGER NOT NULL DEFAULT 0,
              mode TEXT NOT NULL DEFAULT 'choice'
            );

            CREATE INDEX IF NOT EXISTS idx_questions_source ON questions(source_id, enabled);
            CREATE INDEX IF NOT EXISTS idx_reviews_time ON reviews(reviewed_at);
            """
        )
        if db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0:
            seed_demo(db)


def seed_demo(db):
    datasets = [
        ("English demo", "language", "en", "ja", [
            ("en-1", "abandon", "捨てる・放棄する", [], "abandon a plan", ["english", "demo"]),
            ("en-2", "achieve", "達成する", [], "achieve a goal", ["english", "demo"]),
            ("en-3", "adequate", "十分な・適切な", [], "adequate preparation", ["english", "demo"]),
            ("en-4", "ancient", "古代の", [], "ancient history", ["english", "demo"]),
        ]),
        ("Русский demo", "language", "ru", "ja", [
            ("ru-1", "привет", "こんにちは", [], "基本的な挨拶", ["russian", "demo"]),
            ("ru-2", "спасибо", "ありがとう", [], "感謝を表す", ["russian", "demo"]),
            ("ru-3", "книга", "本", [], "名詞・女性名詞", ["russian", "demo"]),
            ("ru-4", "вода", "水", [], "名詞・女性名詞", ["russian", "demo"]),
        ]),
        ("中文 demo", "language", "zh-CN", "ja", [
            ("zh-1", "你好", "こんにちは", [], "nǐ hǎo", ["chinese", "demo"]),
            ("zh-2", "谢谢", "ありがとう", [], "xièxie", ["chinese", "demo"]),
            ("zh-3", "学习", "学習する", [], "xuéxí", ["chinese", "demo"]),
            ("zh-4", "电脑", "コンピューター", [], "diànnǎo", ["chinese", "demo"]),
        ]),
        ("セキスペ demo", "certification", "ja", "ja", [
            ("sc-1", "CSRF対策として最も直接的なものはどれか", "CSRFトークンを検証する", ["CSRFトークンを検証する", "パスワードを長くする", "DNSSECを導入する", "TLS証明書を毎日更新する"], "状態変更リクエストが正規画面から送られたことを検証する。", ["security", "web"]),
            ("sc-2", "SQLインジェクション対策の基本はどれか", "プレースホルダを用いたパラメータ化クエリ", ["プレースホルダを用いたパラメータ化クエリ", "SQL文をBase64化", "DBのポート番号変更", "レスポンスをgzip圧縮"], "入力値をSQL構文へ直接連結せず、値としてバインドする。", ["security", "sql"]),
            ("sc-3", "公開鍵暗号で秘密鍵を保持する主体は誰か", "秘密鍵の所有者本人", ["秘密鍵の所有者本人", "通信相手全員", "認証局だけ", "DNSサーバ"], "秘密鍵は所有者が秘密に保持し、公開鍵のみを配布する。", ["security", "crypto"]),
            ("sc-4", "可用性を主に損なう攻撃の代表例はどれか", "DoS攻撃", ["DoS攻撃", "SQLの正規化", "コード署名", "ハッシュ化"], "DoS/DDoSは資源を枯渇させ、サービスを利用不能にすることを狙う。", ["security", "availability"]),
        ]),
    ]
    t = now()
    for name, category, prompt_lang, answer_lang, questions in datasets:
        cur = db.execute(
            "INSERT INTO sources(name,description,kind,category,default_prompt_lang,default_answer_lang,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (name, "初期デモ。不要なら削除できます。", "manual", category, prompt_lang, answer_lang, t, t),
        )
        source_id = cur.lastrowid
        for external_id, prompt, answer, choices, explanation, tags in questions:
            db.execute(
                """INSERT INTO questions(source_id,external_id,prompt,answer,choices_json,explanation,tags_json,prompt_lang,answer_lang,question_type,enabled,metadata_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id, external_id, prompt, answer, json.dumps(choices, ensure_ascii=False), explanation,
                 json.dumps(tags, ensure_ascii=False), prompt_lang, answer_lang, "auto", 1, "{}", t, t),
            )


def source_dict(row):
    d = dict(row)
    d["question_count"] = d.get("question_count", 0)
    return d


def question_dict(row):
    d = dict(row)
    d["choices"] = json.loads(d.pop("choices_json", "[]") or "[]")
    d["tags"] = json.loads(d.pop("tags_json", "[]") or "[]")
    d["metadata"] = json.loads(d.pop("metadata_json", "{}") or "{}")
    d["enabled"] = bool(d["enabled"])
    return d
