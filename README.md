# Enterprise Knowledge Intelligence Platform

EnKIP is a development-stage knowledge platform for ingesting text and PDF documents, indexing them, and retrieving evidence with tenant and data-source filtering. It provides vector, PostgreSQL lexical, hybrid, and graph-assisted retrieval, plus an Ollama-backed answer/query workflow.

## Architecture

The current implementation uses:

- FastAPI routes for document upload, search, query, and database health.
- A separate polling worker that claims jobs from PostgreSQL's `ingestion_jobs` table.
- PostgreSQL 17 with pgvector for embeddings, `tsvector`/GIN for lexical search, and relational tenant, document, and access data.
- SQLAlchemy models and Alembic migrations, including an explicit pgvector extension prerequisite.
- Local filesystem object storage under `STORAGE_ROOT`.
- Ollama for embeddings, answer generation, query decomposition, and graph extraction.
- A sentence-transformers cross-encoder reranker and evidence/citation validation.
- PostgreSQL entity and relationship tables for graph-assisted candidate retrieval.

The local API entry points are `GET /health`, `POST /tenants/{tenant_id}/documents`,
`POST /tenants/{tenant_id}/search`, and `POST /tenants/{tenant_id}/query`.

## Development Principles

1. Prefer explicit implementations over unnecessary abstractions.
2. Minimize external dependencies.
3. Introduce infrastructure only when justified by a concrete requirement.
4. Keep ingestion and query processing independent.
5. Make expensive operations asynchronous.
6. Make processing stages retryable and idempotent.
7. Treat retrieved documents as untrusted data.
8. Measure retrieval and generation quality rather than relying on subjective evaluation.
9. Design for multi-tenancy from the beginning.
10. Keep components replaceable without coupling the entire system to a single vendor.

## Development Status

Document ingestion, indexing, permission-aware retrieval, and evaluation have
local test coverage. The graph-assisted path is implemented and tested, but
current benchmark ties do not demonstrate a retrieval-quality improvement.
Production authentication, production-scale throughput, deployment hardening,
and broad retrieval quality have not been established.

The search and query routes accept an optional `user_id` query parameter. There
is no `X-User-ID` header wired into the API; sending one has no effect. A
caller-supplied `user_id` and the `tenant_id` path component are development
request context, not authentication or proof of identity. Do not expose this
API as a production service without a separately designed authentication layer.

## Local Development Setup

The commands below use Windows PowerShell from the repository root. The
application requires Python 3.12 or newer. The Compose file provides PostgreSQL
17 with pgvector; Docker Desktop with the `docker compose` command and Ollama
are separate prerequisites. The repository does not pin Docker or Ollama
versions.

### Python Environment

Install `uv` if it is not available, then create and activate a project virtual
environment and install the runtime and development dependency groups:

```powershell
py -3.12 -m pip install uv
uv venv --python 3.12
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
uv sync --locked --group dev
```

The project dependencies are declared in `pyproject.toml`; tests are in its
`dev` dependency group. `uv.lock` pins the resolved dependency graph for Python
3.12 and newer. `--locked` makes setup fail instead of silently changing the
lockfile when project metadata and the lock disagree.

### Environment File

Copy the safe template and replace every angle-bracket placeholder. Do not copy
values from another developer's `.env` file. Keep `.env` local; Git ignores it.

```powershell
if (Test-Path .env) { throw ".env already exists; edit it without overwriting its local settings." }
Copy-Item .env.example .env
```

`apps/api/config.py` loads `.env` from the current working directory. Run
commands from the repository root.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL. Use the database name, user, and password configured by the Compose service. |
| `STORAGE_ROOT` | Local document-object storage path; defaults to `data`. The directory is created when local storage is initialized. |
| `EMBEDDING_MODEL` | Ollama model tag used by ingestion and vector retrieval. |
| `EMBEDDING_DIMENSIONS` | Embedding output size. The current schema stores 1024-dimensional vectors; the selected model and this value must agree. |
| `GENERATION_MODEL` | Ollama chat model used for answer generation and graph extraction. |
| `QUERY_DECOMPOSITION_ENABLED` | Declared setting with a default of `true`; current query handling does not read this flag, so changing it currently has no effect. |
| `DECOMPOSITION_MODEL` | Ollama chat model used by query decomposition. |
| `OLLAMA_BASE_URL` | Ollama API base URL; defaults in code to `http://localhost:11434`. |

One locally verified model pairing is `qwen3-embedding:0.6b` with 1024
dimensions and `llama3.2:3b` for both chat settings. These are not code defaults;
choose compatible tags and put them in `.env`.

### PostgreSQL And Migrations

Start the existing service without deleting its named volume:

```powershell
docker compose -f infrastructure/docker/postgres/docker-compose.yml up -d
docker compose -f infrastructure/docker/postgres/docker-compose.yml ps
```

The pgvector image includes the extension files, but the migrations do not
enable the extension. Enable it once before applying migrations; this is
idempotent and does not reset existing data:

```powershell
docker compose -f infrastructure/docker/postgres/docker-compose.yml exec postgres sh -c "psql -U `$POSTGRES_USER -d `$POSTGRES_DB -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
```

Then apply migrations and check the current revision:

```powershell
python -m alembic upgrade head
python -m alembic current
```

Alembic obtains its URL from `DATABASE_URL` through `migrations/env.py`; the
placeholder URL in `alembic.ini` is not the active connection setting. The
current head also restores the document-chunk lexical GIN index.

Confirm database connectivity and the index without printing connection
settings:

```powershell
python -c "from sqlalchemy import text; from packages.domain.database import SessionLocal; db=SessionLocal(); print(db.scalar(text('SELECT 1'))); db.close()"
python -c "from sqlalchemy import text; from packages.domain.database import SessionLocal; db=SessionLocal(); print(db.scalar(text('SELECT extversion FROM pg_extension WHERE extname = :name'), {'name': 'vector'})); db.close()"
python -c "from sqlalchemy import text; from packages.domain.database import SessionLocal; db=SessionLocal(); print(db.execute(text('SELECT indexdef FROM pg_indexes WHERE indexname = :name'), {'name': 'ix_document_chunks_search_vector'}).scalar_one()); db.close()"
```

The API health endpoint is `GET /health`; it checks the database connection.

### Ollama

Ensure the Ollama service is running. On Windows, use the installed Ollama
service; if it is not running, start `ollama serve` in a separate terminal.
Pull only the tags selected for `EMBEDDING_MODEL`, `GENERATION_MODEL`, and
`DECOMPOSITION_MODEL`. If both chat settings use the same tag, pull it once:
Replace the angle-bracket placeholders below with the exact model tags from
your `.env` before running the commands.

```powershell
ollama pull <value-of-EMBEDDING_MODEL>
ollama pull <value-of-GENERATION_MODEL>
ollama pull <value-of-DECOMPOSITION_MODEL-if-different>
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

The embedding provider calls Ollama's `/api/embed`; generation and
decomposition call `/api/chat`. Retrieval also loads the fixed
`cross-encoder/ms-marco-MiniLM-L-6-v2` sentence-transformers reranker. Its
weights may need to download from Hugging Face on first use; this model is not
configured through `.env`.

### API And Worker

Start the API and worker in separate terminals, both from the repository root
with the virtual environment active:

```powershell
python -m uvicorn apps.api.main:app --reload
```

```powershell
python -m apps.worker.main
```

Verify the API and Ollama independently:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://localhost:11434/api/tags
```

`/health` verifies PostgreSQL only; it does not verify Ollama models. Document
uploads create local files under `STORAGE_ROOT` and enqueue work for the
separate worker.

For local startup failures, inspect the PostgreSQL health/logs, Alembic head,
API database health, and Ollama tags:

```powershell
docker compose -f infrastructure/docker/postgres/docker-compose.yml ps
docker compose -f infrastructure/docker/postgres/docker-compose.yml logs --tail 100 postgres
python -m alembic current
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://localhost:11434/api/tags
```

### Tests And Evaluations

Run focused tests or the full suite:

```powershell
python -m pytest -q tests/unit/test_lexical_search.py tests/unit/test_retrieval_evaluation.py tests/unit/test_retrieval_evaluation_cases.py tests/unit/test_permissions.py tests/integration/test_ingestion_idempotency.py tests/integration/test_permission_aware_retrieval.py tests/integration/test_retrieval_security_boundary.py
python -m pytest -q
```

#### Evaluation Snapshot

The following local reports were generated on 2026-10-04. Recall@5 and MRR@5
are macro-averaged; see the report files for per-case details.

| Dataset | Cases | Vector | Lexical | Hybrid | Graph-assisted hybrid |
|---|---:|---:|---:|---:|---:|
| Baseline | 32 | 1.000 / 0.923 | 1.000 / 1.000 | 1.000 / 0.984 | 1.000 / 0.984 |
| Held-out synthetic | 10 | 1.000 / 1.000 | 0.000 / 0.000 | 1.000 / 1.000 | 1.000 / 1.000 |

Cells show Recall@5 / MRR@5. All 10 held-out lexical cases returned no results;
the other methods had no expected-document misses. Graph-assisted hybrid tied
hybrid on both small datasets, which does not demonstrate an improvement. The
held-out corpus has 11 synthetic documents and 10 manually labeled queries;
these figures are diagnostic, not guarantees of broad retrieval quality or
production performance. See the
[lexical investigation](docs/lexical-retrieval-investigation.md) and the
[matched configuration report](reports/lexical_matched_configuration_comparison.json).

Separate acceptance reports are
`reports/baseline_acceptance_20261004.json` and
`reports/heldout_acceptance_20261004.json`.

The baseline evaluator normally writes
`reports/retrieval_evaluation_report.json`. For an intentional run that keeps
the existing report intact, choose a unique output path:

```powershell
$run = Get-Date -Format 'yyyyMMdd-HHmmss'
python -c "from pathlib import Path; import scripts.evaluate_retrieval as e; e.REPORT_FILE=Path(r'reports/baseline-$run.json'); e.main()"
```

The held-out evaluator seeds its fixed synthetic corpus in a transaction and
rolls it back. Its default output path is
`reports/heldout_retrieval_evaluation_report.json`; do not run it as a tuning
loop. For a deliberate acceptance run, use a new output path and do not run two
copies concurrently:

```powershell
$run = Get-Date -Format 'yyyyMMdd-HHmmss'
python -c "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); import evaluate_heldout_retrieval as e; e.REPORT_FILE=Path(r'reports/heldout-$run.json'); e.main()"
```

The baseline reads the existing evaluation corpus and database. The held-out
runner validates expected IDs and permissions against its synthetic corpus;
after it exits, its transaction rollback should leave no synthetic rows.
Development-only lexical experiments use the same rollback pattern. Do not
manually delete benchmark IDs or drop/reset the database to clean up.

### Stop Services And Limitations

Stop the API and worker with `Ctrl+C` in their terminals. Stop the Compose
service while preserving its database volume with:

```powershell
docker compose -f infrastructure/docker/postgres/docker-compose.yml down
```

Do not add `-v` unless intentionally deleting the local database. Stop the
Ollama service through its Windows service/application controls;
`ollama stop <model>` stops a model runner, not necessarily the Ollama server.
Do not remove model files as part of routine project cleanup.

The platform uses local PostgreSQL, Ollama, local file storage, and a
downloadable reranker. The documented evaluation reports use small manually
labeled or synthetic corpora; they are not production-throughput measurements
or evidence of broad retrieval quality. The current API does not implement
production-grade authentication, and local user/tenant IDs are not an
authentication mechanism.
