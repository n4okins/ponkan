from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.parse
from dataclasses import dataclass

import httpx

from .config import get_settings


@dataclass(slots=True)
class ImportedQuestion:
    external_key: str
    prompt: str
    answer: str
    explanation: str
    question_type: str
    prompt_lang: str
    answer_lang: str
    choices: list[str]
    tags: list[str]
    metadata: dict
    content_hash: str


def normalize_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return normalize_list(parsed)
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in re.split(r"[|;,]", text) if x.strip()]


def google_sheet_csv_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname != "docs.google.com":
        return url
    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        return url
    query = urllib.parse.parse_qs(parsed.query)
    gid = query.get("gid", ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={gid}"


def assert_allowed_url(url: str) -> None:
    settings = get_settings()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("import URL must use https")
    host = parsed.hostname.lower()
    allowed = any(host == item or host.endswith("." + item) for item in settings.import_allowed_hosts)
    if not allowed:
        raise ValueError(f"import host is not allowed: {host}")


def fetch_csv(url: str) -> str:
    settings = get_settings()
    url = google_sheet_csv_url(url)
    assert_allowed_url(url)
    current = url
    with httpx.Client(follow_redirects=False, timeout=20.0) as client:
        for _ in range(6):
            assert_allowed_url(current)
            response = client.get(current, headers={"User-Agent": "Ponkan/3"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("redirect without location")
                current = urllib.parse.urljoin(current, location)
                continue
            response.raise_for_status()
            body = response.content
            break
        else:
            raise ValueError("too many redirects")
    if len(body) > settings.max_import_bytes:
        raise ValueError("import exceeds size limit")
    return body.decode("utf-8-sig")


def parse_csv(text: str, default_prompt_lang: str = "", default_answer_lang: str = "") -> list[ImportedQuestion]:
    result: list[ImportedQuestion] = []
    for index, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        normalized = {str(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        enabled = normalized.get("enabled", "true").lower() not in {"0", "false", "off", "no"}
        if not enabled:
            continue

        prompt = normalized.get("prompt") or normalized.get("word") or normalized.get("question") or ""
        answer = normalized.get("answer") or normalized.get("meaning") or ""
        if not prompt or not answer:
            continue
        external_key = normalized.get("id") or normalized.get("external_id") or f"row-{index}"
        choices = normalize_list(normalized.get("choices"))
        tags = normalize_list(normalized.get("tags"))
        explanation = normalized.get("explanation") or normalized.get("example") or ""
        question_type = normalized.get("question_type") or "auto"
        if question_type not in {"auto", "card", "multiple_choice"}:
            question_type = "auto"
        prompt_lang = normalized.get("prompt_lang") or default_prompt_lang
        answer_lang = normalized.get("answer_lang") or default_answer_lang
        metadata = {
            key: value
            for key, value in normalized.items()
            if key not in {
                "id", "external_id", "prompt", "question", "word", "answer", "meaning", "choices",
                "tags", "explanation", "example", "question_type", "prompt_lang", "answer_lang", "enabled"
            }
            and value
        }
        canonical = json.dumps(
            {
                "prompt": prompt,
                "answer": answer,
                "choices": choices,
                "explanation": explanation,
                "tags": tags,
                "prompt_lang": prompt_lang,
                "answer_lang": answer_lang,
                "question_type": question_type,
                "metadata": metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        result.append(
            ImportedQuestion(
                external_key=external_key,
                prompt=prompt,
                answer=answer,
                explanation=explanation,
                question_type=question_type,
                prompt_lang=prompt_lang,
                answer_lang=answer_lang,
                choices=choices,
                tags=tags,
                metadata=metadata,
                content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            )
        )
    return result
