# Ponkan 3

Ponkan is a self-hosted study platform for vocabulary, languages, certification exams, flashcards, and other recall-based learning.

It provides the same study data through three interfaces:

- Web UI for normal study and content management
- REST API under `/api/v1`
- MCP server under `/mcp/` for ChatGPT, Claude, Codex, and other MCP clients

The learning engine is language-agnostic. English, Russian, Chinese, Japanese certification questions, and arbitrary Q&A can live in the same installation.

## Architecture

```text
Browser / REST client / MCP client
              |
              v
+-----------------------------------------+
| Ponkan app                              |
| FastAPI + React + MCP Python SDK        |
|                                         |
| REST /api/v1   MCP /mcp/   Web UI /     |
|             \      |      /              |
|              Domain services            |
|              SRS scheduler               |
+-------------------+---------------------+
                    |
                    v
               PostgreSQL 16
```

The Web, REST, and MCP paths share one domain/service layer and one database. Learning state is therefore updated consistently regardless of the client used.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the detailed design and database model.

## Main concepts

### Material

A learner-facing unit such as:

- English vocabulary
- Русский basic
- HSK Chinese
- Information Security Specialist / セキスペ
- History
- Internal training

A study session can mix multiple Materials.

### ImportSource

A data source attached to a Material. Google Sheets and public CSV URLs are supported.

`Material` and `ImportSource` are deliberately separate. Removing an import connection does not have to destroy the questions or learning history that came from it.

### Question

The common question model contains:

```text
prompt
answer
explanation
choices
question_type
prompt_lang
answer_lang
tags
metadata
```

Language is metadata, not a special mode, so the same model works for vocabulary and non-language study.

## Database design

Important tables are:

```text
learners
materials
import_sources
sync_runs
questions
question_options
tags
question_tags
study_sessions
review_states
review_events
```

`review_events` is the append-oriented review history. `review_states` is the current derived SRS state for a learner/question pair. This separation makes future scheduler changes and state reconstruction possible without discarding historical answers.

Remote synchronization archives missing questions instead of immediately deleting their learning history.

## Stack

Backend:

- Python 3.12
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic Settings
- MCP Python SDK 2.x

Frontend:

- React 19
- TypeScript
- Vite

Storage / deployment:

- PostgreSQL 16
- Docker
- Docker Compose

Quality:

- pytest
- Ruff
- TypeScript typecheck
- GitHub Actions

## Quick start

Clone the repository and create your environment file:

```bash
git clone https://github.com/n4okins/ponkan.git
cd ponkan
cp .env.example .env
```

At minimum, change `POSTGRES_PASSWORD` in `.env`.

Then start Ponkan:

```bash
docker compose up -d --build
```

Open:

```text
http://<server-ip>:8080/
```

Health check:

```text
http://<server-ip>:8080/api/v1/health
```

MCP endpoint:

```text
http://<server-ip>:8080/mcp/
```

Stop:

```bash
docker compose down
```

Update:

```bash
git pull
docker compose up -d --build
```

PostgreSQL data is stored in the Docker volume `ponkan-db` and survives container recreation.

## Google Sheets / CSV imports

A recommended CSV header is:

```csv
id,prompt,answer,choices,explanation,tags,prompt_lang,answer_lang,question_type,enabled
q1,спасибо,ありがとう,,感謝を表す,russian|basic,ru,ja,auto,true
q2,CSRF対策として直接的なものは？,CSRFトークンを検証する,CSRFトークンを検証する|DNSSEC|Base64化|ポート変更,状態変更要求の正当性を検証する,security|web,ja,ja,multiple_choice,true
```

Legacy vocabulary columns are also accepted and mapped to the generic model:

```csv
id,word,meaning,pronunciation,example,example_ja,part_of_speech,level,tags,enabled
```

`word` becomes `prompt` and `meaning` becomes `answer`.

For Google Sheets, register a shareable Sheet/CSV URL through the Web UI. Remote imports are fetched by the Ponkan server, not by the browser.

For SSRF reduction, remote hosts are allowlisted with `PONKAN_IMPORT_ALLOWED_HOSTS`. Do not widen that list to arbitrary hosts unless the deployment is otherwise isolated.

## MCP

Ponkan exposes Streamable HTTP MCP at `/mcp/`.

Current tools include:

- `list_materials`
- `search_questions`
- `create_study_session`
- `submit_review`
- `create_question`
- `sync_import`
- `get_learning_stats`

Resources include:

- `ponkan://materials`
- `ponkan://stats`

A `daily_review` prompt is also provided for interactive review workflows.

Example MCP client URL:

```text
http://ponkan.home.arpa:8080/mcp/
```

When using a hostname or LAN IP, add it to `PONKAN_MCP_ALLOWED_HOSTS`; MCP DNS-rebinding protection is enabled by default.

## SRS model

Ponkan currently stores, among other fields:

- stability
- difficulty
- due time
- repetitions
- lapses
- streak
- mastery
- response time
- algorithm version

Every submitted review writes a historical `review_event` and updates the current `review_state` in the same transaction.

The scheduler is intentionally isolated behind the service layer so it can later be replaced or migrated to another algorithm without redesigning the Web/API/MCP interfaces.

## Security

The default deployment is intended for a trusted home network.

Do not expose the container port directly to the public Internet without an authentication/TLS layer such as Tailscale, WireGuard, Cloudflare Access, Caddy, nginx, or another reverse proxy.

Optional `PONKAN_API_TOKEN` protects REST and MCP with a bearer token. If you use it, clients must send:

```text
Authorization: Bearer <token>
```

Also review:

- `PONKAN_MCP_ALLOWED_HOSTS`
- `PONKAN_MCP_ALLOWED_ORIGINS`
- `PONKAN_IMPORT_ALLOWED_HOSTS`
- `PONKAN_FORWARDED_ALLOW_IPS`

before exposing Ponkan outside localhost/LAN.

## Development

Backend:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff check src tests
pytest -q
```

Frontend:

```bash
cd web
npm install
npm run typecheck
npm run build
```

Database migrations:

```bash
alembic upgrade head
```

The Docker entrypoint runs Alembic migrations automatically before starting Uvicorn.

## License / content

Ponkan itself is a study platform. Do not redistribute copyrighted commercial wordbooks, exam materials, or other datasets unless you have permission to do so.
