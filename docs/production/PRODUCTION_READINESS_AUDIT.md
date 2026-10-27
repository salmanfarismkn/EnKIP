# EnKIP Production Readiness Gap Audit

**Audit date:** 2026-10-27  
**Scope:** Read-only inspection of the current repository implementation. No application, migration, dependency, environment, database, evaluation-data, or report changes were made. The only file created for this task is this audit.

## Executive summary

EnKIP has a useful development-stage foundation: FastAPI endpoints, PostgreSQL/pgvector persistence, tenant and data-source predicates in retrieval, a polling ingestion worker, document version records, retries, lexical/vector/hybrid/graph retrieval, answer generation, and small evaluation datasets. Those features do not yet establish production security or reliability.

**Do not expose the current API as a production service.** There is no authentication. Tenant and user identifiers come from caller-controlled path/query parameters, while user and data-source administration routes are also unauthenticated. The optional `user_id` is not proof of identity. An unauthenticated caller able to supply a known user's ID can query as that user. In addition, the document-version record does not own its object key: a later upload updates `Document.object_key`, and a worker processing an earlier job reads that shared key. This can index the wrong bytes under a version's checksum and undermines document integrity.

Other material gaps include unbounded upload buffering, no active-version/publication or delete lifecycle, a stale-job recovery mechanism without lease renewal, insufficient retrieval/citation and prompt-injection evaluation, absent deployment/observability/backup evidence, and no load or concurrency acceptance checks.

## Status scale and evidence rules

- **IMPLEMENTED AND VERIFIED** means the behavior exists and was verified against the stated production-relevant acceptance criteria. No domain meets this bar based on this audit.
- **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** means working implementation and some relevant test/evaluation evidence exist, but that evidence does not establish production readiness.
- **PARTIALLY IMPLEMENTED** means material functionality exists but a key part of the domain is missing or unsafe.
- **NOT IMPLEMENTED** means no meaningful implementation was found.
- **NOT APPLICABLE** means the domain does not apply to this project.

Code inspection is not a test result. The test record below states exactly what was executed. Committed evaluation reports are historical repository evidence, not tests run during this audit.

## Domain assessment

| # | Domain | Status | Evidence and assessment |
|---|---|---|---|
| 1 | Authentication and tenant isolation | **PARTIALLY IMPLEMENTED** | Tenant IDs appear in route paths and database filters, but there is no authentication/identity provider or authenticated principal. `user_id` is caller-supplied and optional. Several management routes accept operations without an authorization dependency. See [search.py](../../apps/api/routes/search.py), [query.py](../../apps/api/routes/query.py), [documents.py](../../apps/api/routes/documents.py), [user.py](../../apps/api/routes/user.py), and [README.md](../../README.md). |
| 2 | Authorization across documents, vector search, lexical search, graph retrieval, citations and generated answers | **PARTIALLY IMPLEMENTED** | `PermissionService` filters source IDs; vector, lexical and graph services use those IDs; hybrid query passes the optional user ID. Integration tests assert cross-source filtering. The identity itself is not authenticated, the direct lexical route omits `user_id`, and citation validation checks source-number range rather than claim support. See [service.py](../../packages/permissions/service.py), retrieval services under [packages/retrieval](../../packages/retrieval), [citation_validator.py](../../packages/llm/citation_validator.py), and [test_retrieval_security_boundary.py](../../tests/integration/test_retrieval_security_boundary.py). |
| 3 | Ingestion idempotency, retries, leases, duplicate workers and crash recovery | **PARTIALLY IMPLEMENTED** | There is content hashing, sequential duplicate rejection, `FOR UPDATE SKIP LOCKED`, retry counters, and stale-job recovery. There is no lease heartbeat/claim token, stale recovery can requeue active work, and concurrent duplicate-upload idempotency is not enforced by a database constraint. The ingestion test verifies an injected failure and replay in a transaction, not multiple workers or process crashes. See [document_service.py](../../apps/api/services/document_service.py), [job_queue.py](../../apps/worker/services/job_queue.py), [ingestion_service.py](../../apps/worker/services/ingestion_service.py), and [test_ingestion_idempotency.py](../../tests/integration/test_ingestion_idempotency.py). |
| 4 | Document versioning, atomic publication, deletion, revocation and re-indexing | **PARTIALLY IMPLEMENTED** | Version numbers/checksums and a processing status exist. The storage key is on the shared `Document`, not `DocumentVersion`; searches include chunks from all versions; there is no document delete, active-version, publication, or re-index endpoint. Access grants can be revoked, but that is not document revocation. See [models.py](../../packages/domain/models.py), [document_service.py](../../apps/api/services/document_service.py), [ingestion_service.py](../../apps/worker/services/ingestion_service.py), and [vector_search.py](../../packages/retrieval/vector_search.py). |
| 5 | File validation, size/type limits, parser failure handling and storage integrity | **PARTIALLY IMPLEMENTED** | Empty files are rejected; parsers support PDF, plain text, and Markdown; local storage prevents keys escaping its root; stored byte length is checked. Uploads are read fully into memory, client MIME is trusted, no size/signature/scan limits exist, and length equality does not verify content integrity. Parser failures retry via the job path but do not have a classified failure policy. See [documents.py](../../apps/api/routes/documents.py), [local_storage.py](../../packages/ingestion/local_storage.py), [parser_registry.py](../../packages/ingestion/parser_registry.py), and [pdf_parser.py](../../packages/ingestion/pdf_parser.py). |
| 6 | Retrieval quality, held-out evaluation, citation correctness, prompt-injection resistance and abstention | **PARTIALLY IMPLEMENTED** | Retrieval evaluators, synthetic held-out data, report snapshots, evidence assembly, a citation-number validator, and no-evidence fallback exist. The held-out snapshot has only 10 synthetic cases and lexical retrieval has 0 Recall@5; graph-assisted hybrid ties hybrid. Citation checks do not prove claim/source entailment or require citations, and no prompt-injection/abstention acceptance tests were found. See [evaluation.py](../../packages/retrieval/evaluation.py), [evaluate_heldout_retrieval.py](../../scripts/evaluate_heldout_retrieval.py), [citation_validator.py](../../packages/llm/citation_validator.py), [prompts.py](../../packages/llm/prompts.py), and the [held-out report](../../reports/heldout_acceptance_20261004.json). |
| 7 | Database indexes, query plans, connection pools, migration safety and backup/restore | **PARTIALLY IMPLEMENTED** | Alembic migrations, ordinary tenant/foreign-key indexes, a lexical GIN index, and `pool_pre_ping` exist. No vector ANN index, recorded query-plan/scale test, pool sizing, backup/restore procedure or restore verification was found. pgvector extension creation is a manual prerequisite in the README. See [database.py](../../packages/domain/database.py), [migrations](../../migrations), [docker-compose.yml](../../infrastructure/docker/postgres/docker-compose.yml), and [README.md](../../README.md). |
| 8 | Logs, metrics, tracing, health checks and alerting | **PARTIALLY IMPLEMENTED** | `/health` performs `SELECT 1`; worker/API output uses `print` in relevant paths. There is no observed structured logging, metrics, tracing, dependency health beyond PostgreSQL, alerting, or runbook. See [health.py](../../apps/api/routes/health.py), [ingestion_service.py](../../apps/worker/services/ingestion_service.py), and [main.py](../../apps/worker/main.py). |
| 9 | Rate limits, timeouts, bounded concurrency and resource usage | **PARTIALLY IMPLEMENTED** | Outbound Ollama requests have 120/180-second timeouts, result limits are capped in search/query schemas, and worker polling sleeps between claims. Upload and query body sizes are not bounded; there are no API rate limits, explicit in-flight model-work limits, worker concurrency policy, or end-to-end request/job deadlines. See [schemas](../../apps/api/schemas), [documents.py](../../apps/api/routes/documents.py), [ollama_generation.py](../../packages/llm/ollama_generation.py), and [ollama_decomposition.py](../../packages/llm/ollama_decomposition.py). |
| 10 | Containerization, CI/CD, secrets, deployment, rollback and supply-chain security | **PARTIALLY IMPLEMENTED** | A development PostgreSQL Compose service and locked Python dependency graph exist. The Compose file uses a fixed development password and publishes PostgreSQL's port; there are no API/worker images, deployment/release workflows, rollback process, secret manager, dependency/image scanning or SBOM evidence in tracked files. See [docker-compose.yml](../../infrastructure/docker/postgres/docker-compose.yml), [pyproject.toml](../../pyproject.toml), [uv.lock](../../uv.lock), and [`.env.example`](../../.env.example). |
| 11 | Test coverage, load tests and reproducible acceptance checks | **IMPLEMENTED BUT INSUFFICIENTLY VERIFIED** | Unit and transactional PostgreSQL integration tests and reproducible evaluation scripts exist. This audit ran 19 database-free unit tests successfully; it did not run integration tests or database-backed evaluation. No load, multi-worker race, crash-recovery, deployment, backup-restore, citation-support, or prompt-injection acceptance test was found. See [tests](../../tests), [scripts](../../scripts), and the evaluation reports under [reports](../../reports). |

## Findings

### P0 - Blockers before any production exposure

#### P0-1: No authenticated identity; caller-controlled tenant and user context

- **Evidence (code inspection):** API routes depend on `get_db`, not an authentication/authorization dependency. Search/query accept optional `user_id` from the request query string; `tenant_id` is a path parameter. User creation, access grant/revocation, tenant creation, data-source creation, and document upload are not guarded by an authenticated principal. The `User` model stores email/display name only; no credential or external identity binding is implemented. `README.md` explicitly says the IDs are development context, not proof of identity.
- **Likely failure:** An exposed caller can create tenants/users or grant/revoke access. A caller who knows a permitted user's UUID can supply it as `user_id` and query with that user's access. Tenant path scoping does not authenticate the tenant or caller.
- **Severity:** P0 for any environment reachable by untrusted users; current code is development-only.
- **Remediation:** Select and implement a production identity mechanism; validate the token/session on every protected route; derive tenant and user from verified claims; authorize tenant administration separately; remove caller authority to assert a `user_id`; return fail-closed responses. Add negative tests using two identities/tenants across every API route.
- **Dependencies:** Decide identity provider/claim mapping and tenant membership model before implementing route authorization. This is the first implementation prerequisite.

#### P0-2: Document-version jobs can ingest bytes belonging to a different version

- **Evidence (code inspection):** `DocumentService.create_document` creates a version-specific object key but stores it in `Document.object_key`, overwriting that field on subsequent uploads. `IngestionService.process_job` resolves the job's `DocumentVersion`, then reads `document.object_key`; it does not read a key stored on the version. A queued job for version 1 can therefore read version 2's bytes if version 2 is uploaded before version 1 is processed. The version checksum is not checked against those bytes.
- **Likely failure:** The stored checksum/version number describe one upload while extracted text, chunks, embeddings, graph records, and citations describe another. This is silent data-integrity corruption and can misattribute sources.
- **Severity:** P0 data-integrity blocker.
- **Remediation:** Bind immutable object key and verified checksum to each version; have each job read only that version's object; verify bytes against the recorded checksum before parsing. Define an explicit active/published version and publish a new version atomically only after all derived records succeed.
- **Dependencies:** The version-object association and publication state must be designed before making retrieval version-aware; ensure all search backends use the same published-version policy.

#### P0-3: Unauthenticated, unbounded upload can consume API memory and storage

- **Evidence (code inspection):** `upload_document` calls `await file.read()` without a maximum size or streaming cap. It trusts `UploadFile.content_type`, accepts arbitrary non-empty bytes, and then stores them locally. There is no authentication on the route. PDF/text parsing happens later without resource limits.
- **Likely failure:** A remote caller can upload very large files to exhaust API memory/disk or submit malformed/decompression-heavy files that tie up worker resources; unsupported MIME content creates jobs that later fail.
- **Severity:** P0 exposure blocker when combined with the unauthenticated endpoint; resource controls remain required after authentication.
- **Remediation:** Gate upload behind authorization; enforce request and per-file byte limits while streaming; allow-list extensions and detected content types; apply parser-specific page/text/resource limits; reject unsupported files before committing a document/job; monitor storage quotas.
- **Dependencies:** Authentication/tenant authorization (P0-1), then file policy and parser limits. Do not rely on reverse-proxy limits alone.

### P1 - Required for a credible controlled pilot

#### P1-1: ACL behavior is inconsistent across routes and does not have a single fail-closed policy

- **Evidence (code inspection):** `PermissionService` returns every tenant data source when `user_id is None` and no `DataSourceAccess` row exists; once any access grant is configured, it returns an empty set for a missing user. The direct `/search/lexical` endpoint does not accept or forward `user_id`, unlike hybrid search/query. Search services scope returned content by accessible data-source IDs, but the access context remains unauthenticated.
- **Likely failure:** Anonymous lexical requests can search all sources in tenants without configured grants; in tenants with grants, the same endpoint silently returns no results. A missing grant setup changes behavior from broad access to empty results.
- **Severity:** P1 correctness/configuration issue; becomes a P0 data exposure concern until authenticated identity is established.
- **Remediation:** Make identity mandatory for protected retrieval; use one authorization dependency and policy for all search/query endpoints; default to deny; include direct lexical route in the same policy. Add tests for missing identity, unassigned users, revoked grants, cross-tenant IDs, and each retrieval backend.
- **Dependencies:** P0-1; align the route behavior before declaring P0-1 complete.

#### P1-2: Version lifecycle lacks atomic publication, deletion and re-index/revocation behavior

- **Evidence (code inspection):** Search joins chunks to all document versions and does not filter `processing_status` or an active-version marker. There is no document delete route or object cleanup path. Ingestion creates new versions but does not deactivate prior chunks. Data-source grants can be revoked, but no document-level revocation or re-index lifecycle exists.
- **Likely failure:** Old and new content can both appear in results; failed updates leave old content indefinitely visible; deletion cannot remove the object and all derived records; re-indexing cannot reliably replace a published snapshot.
- **Severity:** P1, with P0 implications for regulated data revocation or stale confidential content.
- **Remediation:** Introduce a documented active-version/publication state; only retrieve published versions; implement deletion/revocation across object storage, chunks, embeddings, lexical vectors, graph records and caches; define recoverable cleanup/re-index operations and audit trail.
- **Dependencies:** P0-2; complete version-specific object handling first.

#### P1-3: Worker lease recovery can cause duplicate active processing; retries are not production-grade

- **Evidence (code inspection):** `JobQueue.claim_next` marks a pending job processing with `claimed_at` and commits; `recover_stale_jobs` resets every processing job older than 15 minutes without heartbeat/ownership fencing. Long model/PDF work can exceed that window. `IngestionService` retries immediately until `max_attempts`, with no backoff/jitter; stale recovery does not check the attempt limit. The exception path sets `error_message` but not `last_error` or `DocumentVersion.processing_error`.
- **Likely failure:** A second worker may reclaim a job while the first is still embedding/extracting; both may perform external work and conflict or produce repeated side effects. A poison file can be retried rapidly; error state may be inconsistent.
- **Severity:** P1 reliability/data-integrity risk.
- **Remediation:** Use a renewable lease plus claim/lease token fencing; atomically claim and verify ownership on completion; add bounded exponential backoff/jitter and terminal/dead-letter handling; define stale-job and max-attempt policy; persist structured error classification consistently. Test two workers, lease expiry, process termination at each stage, and replay.
- **Dependencies:** P0-2 version-specific object identity; transactional idempotency constraints; then multi-worker fault tests.

#### P1-4: Idempotency test coverage does not cover concurrent uploads or worker races

- **Evidence (code inspection):** The existing integration test verifies duplicate bytes sequentially and checks one injected graph-persistence failure followed by replay. Duplicate detection is an application query; the schema constrains checksum per document, but does not enforce uniqueness across tenant/data source or title under concurrent document creation. The test uses a transaction/savepoint and one session; no parallel worker test exists.
- **Likely failure:** Simultaneous same-file uploads can pass the pre-insert duplicate check and create separate documents; concurrent processing can race on chunks/graph records.
- **Severity:** P1.
- **Remediation:** Define the idempotency key and enforce it with database uniqueness/locking, handle expected conflicts, and add real PostgreSQL concurrency tests. Preserve the existing transactional rollback style where it truly isolates records, but test outside a shared-session sequential replay too.
- **Dependencies:** P0-2 and P1-3.

#### P1-5: Retrieval/citation evidence is not adequate to establish trustworthy answers

- **Evidence (code inspection):** `CitationValidator.validate` only rejects citation numbers outside `1..len(evidence)`; it accepts answers with no citations and does not associate claims with supporting passages. The system prompt instructs the model to cite and use sources but does not clearly isolate or label retrieved text as untrusted instructions. The query service abstains when no evidence is returned or citation numbers are invalid, not when evidence is weak or claims are unsupported. No prompt-injection or claim-support acceptance tests were found.
- **Evidence (historical evaluation):** The 2026-10-04 held-out report covers 10 synthetic queries: vector/hybrid/graph-assisted hybrid report Recall@5 and MRR@5 of 1.0; lexical reports 0.0 for both. The baseline report covers 32 labeled cases. Graph-assisted hybrid ties hybrid on these snapshots; this is not broad quality evidence. No report measures answer factuality, citation precision/recall, injection resistance, or abstention calibration.
- **Likely failure:** A plausible-looking unsupported answer or a source-injected instruction can influence generated output; a syntactically valid but unrelated citation passes validation.
- **Severity:** P1 for enterprise answer reliability; P0 if this is used for high-impact decisions without human review.
- **Remediation:** Add adversarial untrusted-document tests; evaluate answer claims against citations and source spans; require citations for factual claims; evaluate citation correctness, abstention and refusal behavior on human-reviewed held-out cases; broaden datasets across tenants, document formats and hard negatives. Keep retrieval and answer quality metrics separate.
- **Dependencies:** Stable version/access filtering (P0-2/P1-2) so tests evaluate the correct evidence set.

#### P1-6: File processing and local storage do not establish durable, verified object integrity

- **Evidence (code inspection):** The route trusts client MIME; parsers select by MIME string and PDF parsing has no explicit page/size/resource cap. `DocumentService` rereads the stored object and compares only lengths, not hashes. Local storage is an unencrypted filesystem implementation; no durability/replication/backup integration is present. Failures after object write but before database commit can leave an orphan.
- **Likely failure:** Content can be mislabeled, malicious or too large; a same-length truncation/corruption is not detected; host/disk loss loses originals; failed commits leave untracked files.
- **Severity:** P1.
- **Remediation:** Validate content independently of client headers, enforce file/parser budgets, verify SHA-256 after write/read, use durable storage appropriate to the deployment, and add an orphan reconciliation/cleanup process with auditable deletion.
- **Dependencies:** P0-3 and P0-2.

#### P1-7: Database operational safety and performance are unmeasured

- **Evidence (code inspection):** `database.py` only enables `pool_pre_ping`; no pool sizing/overflow, statement timeout, or pool metrics are configured. Migrations create ordinary indexes and lexical GIN; no HNSW/IVFFlat vector index was found. Evaluation code reports elapsed strategy times but does not establish query plans or production-scale behavior. README requires manual `CREATE EXTENSION vector`; no backup/restore or restore verification instructions were found.
- **Likely failure:** Vector search degrades to scans as data grows; connection exhaustion or long queries can harm API/worker availability; upgrades or data loss lack a demonstrated recovery path.
- **Severity:** P1 operational readiness; vector indexing/optimization may remain P2 until measured.
- **Remediation:** Establish migration/upgrade rehearsal and rollback limits; automate extension prerequisites; define pool/timeouts from deployment capacity; capture `EXPLAIN (ANALYZE, BUFFERS)` on representative data; benchmark vector index choices against recall/latency; implement and periodically restore-test backups.
- **Dependencies:** Establish pilot dataset/workload and version/access correctness before interpreting plans or benchmarks.

#### P1-8: Health and telemetry are insufficient to operate or diagnose a pilot

- **Evidence (code inspection):** `/health` returns success after `SELECT 1` only. It does not expose worker queue age, storage availability, model readiness or dependency status. Worker/API paths use `print`; no structured log fields, metrics, tracing, alert definitions or operational runbooks were found.
- **Likely failure:** A healthy database response can mask a stopped worker, unavailable Ollama, exhausted storage or a growing failed-job queue; failures will be difficult to correlate.
- **Severity:** P1.
- **Remediation:** Add structured logs with request/job/version IDs and redaction; expose separate liveness/readiness checks; record queue age, retry/failure counts, latency and resource metrics; alert on actionable thresholds; document recovery steps. Avoid reporting secrets or source text in telemetry.
- **Dependencies:** Define service ownership and deployment topology; do not make health checks synchronously load large models.

#### P1-9: No explicit API throttling or end-to-end resource budget

- **Evidence (code inspection):** Search/query counts have schema upper bounds and outbound Ollama calls have request timeouts, but query strings have no maximum length, upload is unbounded, and there are no rate limits or explicit concurrency budgets for model/reranker calls. Query decomposition may produce up to five subqueries and runs retrieval for each.
- **Likely failure:** A small number of callers can monopolize database/model capacity with long queries, large uploads, parallel API requests or repeated decomposition/generation calls.
- **Severity:** P1 for a shared pilot.
- **Remediation:** Add request/upload limits, per-identity and per-tenant rate/concurrency budgets, database statement timeouts and job deadlines; bound candidate/evidence/token sizes and model work. Tune limits using load measurements, not guesses.
- **Dependencies:** P0-1 identity; P1-8 telemetry and a defined pilot capacity.

#### P1-10: Production deployment and release controls are absent

- **Evidence (code inspection):** Compose contains only PostgreSQL, pins the image by a mutable major tag, hardcodes `knowledge_dev` as a password, and maps port 5432 to the host. Tracked files contain no API/worker container build, CI workflow, deployment workflow, secret manager integration, rollback procedure, or dependency/image scan configuration. Python dependencies are lockfile-backed, which is useful but does not cover image/model artifacts.
- **Likely failure:** Developers may deploy with development credentials/default network exposure; releases cannot be promoted or rolled back reproducibly; vulnerable dependencies/images are not detected by repository automation.
- **Severity:** P1 before an external pilot.
- **Remediation:** Keep the existing simple API + worker + PostgreSQL architecture, but define environment-specific secrets/network policy, reproducible API/worker packaging, CI test and migration checks, staged deployment/rollback, image/dependency scanning and model artifact provenance. Do not commit credentials.
- **Dependencies:** P0 security controls; deployment target and data-residency requirements.

### P2 - Measure and mature after P0/P1 controls

#### P2-1: Retrieval scalability and ranking improvements need workload evidence

- **Evidence:** No vector ANN index is present; graph candidate lookup uses bounded `ILIKE` matching; current evaluation corpus is small and synthetic/manual. The graph strategy ties hybrid on the committed snapshots. These facts show unmeasured scaling/quality, not that a new database or service is required.
- **Remediation:** Collect representative query/doc/tenant volume and latency targets; profile PostgreSQL query plans; add a vector index only if it meets measured recall/latency needs; tune lexical/hybrid/reranking; retain PostgreSQL and the current worker until a measured bottleneck justifies a change.
- **Dependencies:** P1-7 and P1-9.

#### P2-2: Evaluation snapshots are not yet a reproducible release gate

- **Evidence:** Evaluation scripts read the configured database and some write fixed report paths; the held-out script seeds a synthetic corpus in a transaction and rolls it back. Existing snapshots are dated 2026-10-04, manually labeled/synthetic and do not test generated answers. The decomposition-enabled setting is declared in config but not read by runtime query handling.
- **Remediation:** Make dataset/model/config versioning explicit, use unique output paths in CI, add deterministic acceptance thresholds and a human-reviewed answer/citation suite, and make all feature flags effective or remove the unused setting. Keep benchmark runs isolated from production data.
- **Dependencies:** P1-5 and safe disposable test infrastructure.

#### P2-3: Tracked database artifact needs a data-handling decision

- **Evidence:** `app.db` is a tracked repository file. Its contents were deliberately not inspected as part of this read-only audit; this report cannot determine whether it contains only disposable development data.
- **Remediation:** Have the project owner verify its contents and intended role. If it contains customer, credential, or other sensitive data, follow the repository's approved incident/history-remediation process; do not merely assume `.gitignore` protects an already tracked file.
- **Dependencies:** Owner review before any public repository or artifact distribution.

## Recommended prioritized roadmap

The smallest practical plan is to harden the existing FastAPI + PostgreSQL + worker architecture. This audit does **not** find evidence requiring Kubernetes, Kafka, a separate vector database, or a graph database.

### P0 - Security and data integrity

1. **Identity and authorization boundary (P0-1, P1-1):** Select an identity source; authenticate every protected route; derive tenant/user context from trusted claims; authorize tenant administration; make all retrieval fail closed; unify lexical/vector/graph/query policies. Add cross-tenant and spoofed-user tests.
2. **Version-safe ingestion/publication (P0-2, P1-2):** Store immutable object key/checksum on `DocumentVersion`; verify checksum in the worker; define active/published status; publish atomically; filter every retrieval path to the same eligible version. Add tests for two queued versions and failed publication.
3. **Bounded authorized upload (P0-3, P1-6):** Require authorization, cap bytes while streaming, validate actual file type, constrain PDF parsing, verify stored checksum, and define orphan cleanup. Reject invalid inputs before enqueuing jobs.
4. **Repository data review (P2-3):** Owner verifies whether tracked `app.db` is intended and contains no sensitive information. This is a review action, not an assumption that it is unsafe.

### P1 - Credible pilot reliability

5. **Queue correctness and retry safety (P1-3, P1-4):** Add renewable/fenced leases, bounded retry backoff and terminal failure handling; enforce idempotency in PostgreSQL; test concurrent uploads/workers and process death.
6. **Revocation/deletion/re-indexing (P1-2):** Add a lifecycle operation that removes/invalidates original and derived data consistently, with auditability and recovery.
7. **Answer and retrieval acceptance (P1-5):** Add held-out, human-reviewed test cases for tenant/access boundaries, prompt injection, citations tied to claims, weak-evidence abstention, and supported answers; make thresholds reproducible and release-blocking.
8. **Operational baseline (P1-7 to P1-10):** Add structured logs, actionable metrics/health, capacity limits, backup/restore drills, migration rehearsal, CI for tests/build/migrations, secrets/network controls, and a rollback path.

### P2 - Evidence-led maturity

9. **Measure before optimizing:** Run representative query-plan and load tests; add/tune vector indexes and pool sizes only against recall/latency objectives. Expand quality datasets and cost/latency tracking. Continue using the current PostgreSQL and worker setup unless measurements show a concrete limit.

## Verification performed and evidence gaps

- **Executed:** `python -m pytest -q -p no:cacheprovider` against `tests/unit/test_chunker.py`, `test_citations.py`, `test_retrieval_evaluation.py`, `test_retrieval_evaluation_cases.py`, `test_rrf.py`, `test_text_parser.py`, and `test_pdf_parser.py` using the repository virtual environment. Result: **19 passed in 0.24s**. These tests are database-free and do not verify production readiness.
- **Not executed:** PostgreSQL integration tests, the smoke test, live retrieval evaluations, held-out evaluation, worker execution, migrations, Docker/Compose, Ollama calls, or load tests. Some repository tests call `Base.metadata.create_all`, use the configured live database, or seed database-backed corpora; those were not run to preserve the existing database and reports.
- **Inspected but not re-run:** Integration tests for sequential ingestion replay and source-level retrieval permissions; evaluation snapshots dated 2026-10-04. Their presence is evidence of intended behavior, not independent proof that current configured infrastructure passes.
- **Not inspected:** Contents of `app.db`, `.env`, secrets, live database contents, or deployed infrastructure. No query plans, restore drills, security scan, load profile, or production telemetry were available.

## First implementation milestone

Start with a **secure, version-correct vertical slice**: authenticate a request; resolve its tenant/user from trusted identity; authorize upload and retrieval; store immutable per-version object identity and checksum; process only that version; atomically publish it; and verify that vector, lexical, graph, citations, and generated answers cannot return another tenant's or an unpublished version's content. Add bounded upload limits and database-backed negative/concurrency tests as part of this milestone. Do not start with scaling infrastructure; close the identity and document-integrity gaps first.
