# EnKIP Production Readiness Gap Audit

**Audit date:** 2026-11-03

**Scope:** Repository inspection plus focused verification performed after the P0 authentication, authorization, version-integrity, and upload-hardening changes.

This document describes the implementation as it exists now, not the earlier development baseline. Code inspection is separated from executed tests, and no database-backed result is reported as passed unless it ran against the explicitly isolated PostgreSQL environment.

## Executive summary

EnKIP now has provider-neutral OIDC/JWT authentication, internal identity mapping,
tenant-admin authorization, live data-source grants, permission-aware retrieval,
immutable version object keys, streamed upload limits, worker recovery controls,
container deployment, and isolated backup/restore utilities.

PostgreSQL acceptance and deployment acceptance were subsequently completed
against disposable environments. The evidence does not establish production
capacity or production-environment readiness: renewable worker leases, answer
factuality and prompt-injection resistance, rate limiting, production TLS,
external Ollama operation, supply-chain scanning, and production-scale database
capacity remain unverified or incomplete.

**Do not treat passing unit tests as proof of production security.**

## Status scale

- **IMPLEMENTED AND VERIFIED:** Behavior exists and relevant acceptance evidence was executed successfully.
- **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED:** Working implementation exists, with some tests or inspection, but evidence is incomplete.
- **PARTIALLY IMPLEMENTED:** Material functionality exists but a required control, lifecycle, or acceptance path is missing.
- **NOT IMPLEMENTED:** No meaningful implementation was found.
- **NOT APPLICABLE:** The domain does not apply to this project.

## Domain assessment

| # | Domain | Status | Evidence and assessment |
|---|---|---|---|
| 1 | Authentication and tenant isolation | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | OIDC validation, issuer/audience/JWKS checks, external identity mapping, disabled-user rejection, and tenant-derived principals exist in [auth.py](../../apps/api/auth.py). Development auth is explicitly environment-gated. Tenant membership checks exist in protected route dependencies. Unit HTTP coverage exists, but PostgreSQL migration and live identity behavior remain unexecuted in this environment. See [7f4c2a9e1b6d](../../migrations/versions/7f4c2a9e1b6d_add_oidc_identity_mapping.py). |
| 2 | Authorization across documents, vector, lexical, graph, citations and answers | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | Tenant-admin checks protect user, data-source, grant, and upload administration; the list-self-grants endpoint prevents another-user access. Live `DataSourceAccess` rows filter vector, lexical, graph, hybrid, reranked, and query-evidence paths through [service.py](../../packages/permissions/service.py). Disabled users and cross-tenant principals are rejected centrally. Inspection does not establish these filters survive revoked-access integration, because PostgreSQL acceptance is blocked. See [test_authorization_http.py](../../tests/unit/test_authorization_http.py) and [test_retrieval_security_boundary.py](../../tests/integration/test_retrieval_security_boundary.py). |
| 3 | Ingestion idempotency, retries, leases, duplicate workers and crash recovery | **PARTIALLY IMPLEMENTED** | Content hashing, retry counters, `FOR UPDATE SKIP LOCKED`, stale retry logic, transaction handling, and a sequential worker remain. There is still no renewable lease, claim-fencing token, terminal/dead-letter policy, or demonstrated two-worker crash replay. See [job_queue.py](../../apps/worker/services/job_queue.py), [ingestion_service.py](../../apps/worker/services/ingestion_service.py), and [test_ingestion_idempotency.py](../../tests/integration/test_ingestion_idempotency.py). |
| 4 | Document versioning, atomic publication, deletion, revocation and re-indexing | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | Per-version source keys, checksums, processing state, worker verification, source-size/chunk limits, and commit-failure cleanup are implemented. See [2c28e0a1f48d](../../migrations/versions/2c28e0a1f48d_bind_jobs_to_version_sources.py), [document_service.py](../../apps/api/services/document_service.py), and [local_storage.py](../../packages/ingestion/local_storage.py). No active-version/publication lifecycle, document delete/revoke, or re-index operation was found. PostgreSQL commit-failure and source-key acceptance is not executed in this environment. |
| 5 | File validation, size/type limits, parser failure handling and storage integrity | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | Uploads stream in 64 KiB reads and enforce `MAX_UPLOAD_BYTES`; validation rejects empty, unsupported, malformed UTF-8, malformed/encrypted PDFs and PDFs above the configured page limit. Storage uses temporary files and per-version keys. Source-size and chunk-count guards are applied in the worker. Unit tests cover these behaviors, but real streamed-byte and commit-failure behavior remains PostgreSQL/storage acceptance-blocked. See [documents.py](../../apps/api/routes/documents.py), [upload_validation.py](../../packages/ingestion/upload_validation.py), [local_storage.py](../../packages/ingestion/local_storage.py), and [test_upload_security.py](../../tests/unit/test_upload_security.py). |
| 6 | Retrieval quality, citation correctness, prompt-injection resistance and abstention | **PARTIALLY IMPLEMENTED** | Retrieval strategies, evidence assembly, evidence-number validation, and no-evidence fallback exist. The citation validator does not prove claim support, prompt-injection resistance has no acceptance suite, and abstention is not calibrated. The historical held-out report does not measure answer factuality, citation precision or injection resistance. See [citation_validator.py](../../packages/llm/citation_validator.py), [query_service.py](../../packages/retrieval/query_service.py), and [reports/heldout_acceptance_20261004.json](../../reports/heldout_acceptance_20261004.json). |
| 7 | Database indexes, query plans, pools, migration safety and backup/restore | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | Alembic, tenant/user indexes, lexical GIN, foreign keys, `pool_pre_ping`, migration guards, custom-format backups, source manifests, isolated restore, and checksum verification exist. Fresh/upgrade migration acceptance and utility-driven restore were executed against disposable PostgreSQL 17.11/pgvector 0.8.6. Production pool sizing, vector ANN selection, coordinated snapshots, and production-scale query plans remain unverified. See [database.py](../../packages/domain/database.py), [migrations](../../migrations), and [compose.production.yml](../../infrastructure/docker/compose.production.yml). |
| 8 | Logs, metrics, tracing, health checks and alerting | **PARTIALLY IMPLEMENTED** | `/health` checks PostgreSQL and current worker/API paths have limited console output. No structured redacted logging, metrics, tracing, queue-age/dependency readiness telemetry, alert rules, or runbook is established. See [health.py](../../apps/api/routes/health.py), [main.py](../../apps/worker/main.py), and [ingestion_service.py](../../apps/worker/services/ingestion_service.py). |
| 9 | Rate limits, timeouts, concurrency and resource usage | **PARTIALLY IMPLEMENTED** | Upload limits, parser/page limits, worker source/chunk guards, sequential worker execution, outbound model timeout configuration, and request candidate limits provide bounded behavior in several paths. No API/tenant rate limit, queue concurrency budget, database statement timeout, or load-derived request budget is established. A parser cannot cancel an already-running parse through the current interfaces. See [config.py](../../apps/api/config.py), [main.py](../../apps/worker/main.py), and [query.py](../../apps/api/routes/query.py). |
| 10 | Containerization, CI/CD, secrets, deployment, rollback and supply chain | **PARTIALLY IMPLEMENTED** | A shared non-root API/worker image, separate migration/API/worker Compose services, persistent volumes, controlled migrations, explicit environment configuration, and deployment acceptance script exist. CI/CD, production secret management, rollback automation, image/dependency scanning, signing, and production reverse-proxy/TLS policy remain unverified. See [Dockerfile](../../Dockerfile), [compose.production.yml](../../infrastructure/docker/compose.production.yml), and `uv.lock`. |
| 11 | Test coverage, load tests and reproducible acceptance | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | Unit tests cover uploads, authentication, HTTP administration, citations, chunking, and parsers. PostgreSQL integration tests cover designed authorization/version behaviors but were not run successfully in the latest acceptance environment. No load, migration upgrade, multi-worker crash, restore, or reproducible release threshold was executed. |

## Route-to-policy inventory

| Surface | Implemented policy |
|---|---|
| Tenant creation | Denied through the API as system-level; no public self-promotion path. |
| User creation and disablement | Tenant admin required; caller tenant must match the authenticated tenant; disabling removes live data-source grants. |
| Data-source creation | Tenant admin required; tenant ownership is server-derived and resource IDs are tenant-scoped. |
| Data-source grant/revoke/list | Tenant admin for mutation; ordinary users may only list their own grants. |
| Document upload | Authenticated tenant admin, tenant membership, and server-owned data-source tenant match required; streamed limits and validation apply. |
| Search and query | Authenticated membership required; live grants filter candidates before retrieval/evidence assembly. |
| Vector, lexical, graph, hybrid | `PermissionService` resolves only enabled users with matching tenant membership and currently granted sources. |
| Citations/download/source metadata | Evidence and source paths depend on permission-aware retrieval; database-backed citation isolation remains unexecuted. |
| System operations | Tenant membership or tenant admin does not grant system-level tenant creation privileges. |

## Known security and integrity risks

### Critical

- **PostgreSQL acceptance is not available.** Cross-tenant, revoked-grant, disabled-user, migration, vector/lexical/graph, and commit-failure behavior is not currently verified against disposable PostgreSQL/pgvector.
- **No document lifecycle.** There is no delete, revoke, publication, re-index, or active-version operation in the inspected HTTP/API surface.

### High

- **Worker crash correctness remains lease-incomplete.** Stale jobs can recover, but renewable/fenced leases and concurrent-worker crash replay are not established.
- **Answer and citation quality remains unproven.** Citation syntax is not claim entailment, and prompt-injection resistance/abstention lacks an acceptance suite.

### Medium

- **Deployment controls are immature.** No production image/release, secrets policy, rollback, scanning, alerts, or backup restore drill is established.
- **Database scale is unmeasured.** No query plans, pool thresholds, connection-timeouts, vector-index benchmark, or restore drill is recorded.

## Prioritized roadmap

### P0

1. **Close PostgreSQL acceptance closure:** configure an approved disposable PostgreSQL 17/pgvector instance and run migrations, fresh/upgrade migration paths, HTTP authorization, revoke/disable, retrieval isolation, and upload commit-failure tests.
2. **Complete version lifecycle fencing:** define publication/active-version semantics, add delete/revoke/re-index operations, and test failed publication, duplicate workers, and old-version isolation.
3. **Fenced queue crash recovery:** add renewable leases, atomic claim ownership, bounded backoff, terminal failure handling, and multi-worker/process-crash tests before scaling worker concurrency.

### P1

1. **Answer trust acceptance:** add tenant-safe claim/citation tests, prompt-injection tests, weak-evidence abstention, and human-reviewed held-out cases.
2. **Operational baseline:** add structured redacted logs, readiness/dependency health, queue metrics, alert thresholds, backup/restore and migration rehearsal.
3. **Request and model budgets:** add per-tenant/per-user rate limits where API exposure is shared, statement/decomposition timeouts, bounded concurrency, and load-derived limits.
4. **Deployment security:** add API/worker containers, CI migration/tests, secret management, image/dependency scanning, and rollback documentation.

### P2

1. Measure PostgreSQL query plans and benchmark latency/recall before selecting vector indexes.
2. Expand retrieval quality datasets and make evaluation thresholds reproducible release gates.
3. Add cost, latency, resource, and tenant-isolation dashboards after pilot workload targets exist.

## Verification performed

### Executed successfully

- Earlier focused and full-suite runs are preserved as historical evidence and
  are not combined into a single total.
- PostgreSQL-backed suite: **84 passed, 2 skipped** in the latest applicable
  run; skips were the opt-in performance benchmark and separately provisioned
  retrieval evaluation dataset.
- PostgreSQL 17.11 with pgvector 0.8.6, including fresh migration to
  `c4a91e2d7b55`.
- Deployment Compose acceptance, API/worker restart, SIGTERM handling, named
  source-volume persistence, and non-root runtime verification.
- Utility-driven custom-format backup and isolated restore with source
  manifests, checksums, embeddings, grants, and authorized retrieval.
- Python byte compilation, `uv lock --check`, `git diff --check`, and Alembic
  head verification.

### Not verified or incomplete

- Production-scale capacity, rate limiting, TLS/reverse proxy, CI/CD,
  supply-chain scanning, rollback automation, and cloud deployment.
- Live Ollama integration through the production Compose deployment.
- Transactionally coordinated database/filesystem snapshots.
- Renewable worker leases or claim fencing for stale-job recovery.
- Answer factuality, calibrated abstention, and prompt-injection resistance.
