"""Diagnose PostgreSQL lexical matching on a disposable synthetic corpus."""

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from packages.domain.database import SessionLocal, engine
from packages.permissions.service import PermissionService
from packages.retrieval.lexical_search import LexicalSearchService
from lexical_dev_corpus import (
    DEVELOPMENT_DOCUMENTS,
    TENANT_ID,
    DevelopmentCorpus,
    seed_development_corpus,
)


BASELINE_CASES_FILE = Path("tests/evaluation/retrieval_cases.json")
DEVELOPMENT_CASES_FILE = Path("tests/evaluation/lexical_development_cases.json")
REPORT_FILE = Path("reports/lexical_development_experiment_report.json")
DEVELOPMENT_TENANT_IDS = [TENANT_ID]


def _case_diagnostic(
    db: Session,
    case: dict,
    corpus: DevelopmentCorpus | None,
) -> dict:
    tenant_id = UUID(case["tenant_id"])
    user_id = UUID(case["user_id"])
    expected_ids = [UUID(value) for value in case["expected_document_ids"]]
    query = case["query"]
    permission_service = PermissionService()
    allowed_sources = permission_service.get_accessible_data_source_ids(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
    )

    expected_document_details = []
    for document_id in expected_ids:
        rows = db.execute(
            text("""
                SELECT d.id, d.tenant_id, d.data_source_id, c.id,
                       c.search_vector IS NOT NULL AS vector_present,
                       c.search_vector <> ''::tsvector AS vector_nonempty,
                       c.search_vector @@ websearch_to_tsquery('english', :query)
                           AS direct_match
                FROM documents d
                JOIN document_versions v ON v.document_id = d.id
                JOIN document_chunks c ON c.document_version_id = v.id
                WHERE d.id = :document_id AND d.tenant_id = :tenant_id
                ORDER BY c.chunk_index
            """),
            {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "query": query,
            },
        ).all()
        accessible = bool(rows and rows[0][2] in allowed_sources)
        detail = {
            "document_id": str(document_id),
            "exists_in_tenant": bool(rows),
            "accessible_to_user": accessible,
            "chunk_count": len(rows),
            "non_null_vector_chunks": sum(bool(row[4]) for row in rows),
            "nonempty_vector_chunks": sum(bool(row[5]) for row in rows),
            "direct_matching_chunks": sum(bool(row[6]) for row in rows),
        }
        if corpus is not None and document_id in corpus.document_context:
            lexemes = db.execute(
                text("""
                    SELECT COALESCE(
                        array_agg(DISTINCT token.lexeme ORDER BY token.lexeme),
                        ARRAY[]::text[]
                    )
                    FROM documents d
                    JOIN document_versions v ON v.document_id = d.id
                    JOIN document_chunks c ON c.document_version_id = v.id
                    CROSS JOIN LATERAL
                        unnest(tsvector_to_array(c.search_vector)) AS token(lexeme)
                    WHERE d.id = :document_id AND d.tenant_id = :tenant_id
                """),
                {"document_id": document_id, "tenant_id": tenant_id},
            ).scalar_one()
            detail["indexed_lexemes"] = lexemes
        expected_document_details.append(detail)

    tsquery = db.execute(
        text("SELECT websearch_to_tsquery('english', :query)::text"),
        {"query": query},
    ).scalar_one()
    service_results = LexicalSearchService(db=db).search(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        query=query,
        limit=1000,
    )
    returned_ids = {result["document_id"] for result in service_results}
    expected_returned = [document_id in returned_ids for document_id in expected_ids]
    expected_access = all(
        detail["accessible_to_user"] for detail in expected_document_details
    )
    if corpus is not None and expected_access != case["expected_access"]:
        raise AssertionError(
            f"Access label disagrees with seeded permissions in {case['case_id']}"
        )

    return {
        "case_id": case["case_id"],
        "case_kind": case.get("case_kind", "baseline"),
        "query": query,
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "expected_document_ids": [str(value) for value in expected_ids],
        "expected_access": expected_access,
        "query_tsquery": tsquery,
        "expected_documents": expected_document_details,
        "service_returned_expected": expected_returned,
        "service_result_count": len(service_results),
        "diagnosis": (
            "expected document retrieved"
            if expected_access and all(expected_returned)
            else "authorized lexical miss"
            if expected_access
            else "unauthorized expected document withheld"
            if not any(expected_returned)
            else "PERMISSION VIOLATION"
        ),
    }


def _read_search_configuration(db: Session) -> dict:
    search_config = db.execute(
        text("SELECT current_setting('default_text_search_config')")
    ).scalar_one()
    trigger = db.execute(
        text("""
            SELECT t.tgenabled, pg_get_triggerdef(t.oid)
            FROM pg_trigger t
            WHERE t.tgrelid = 'document_chunks'::regclass
              AND t.tgname = 'document_chunks_search_vector_trigger'
              AND NOT t.tgisinternal
        """)
    ).one_or_none()
    has_gin_index = db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'document_chunks'
                  AND indexname = 'ix_document_chunks_search_vector'
            )
        """)
    ).scalar_one()
    return {
        "postgres_default_text_search_config": search_config,
        "query_and_index_config": "english",
        "insert_update_trigger_present": trigger is not None,
        "insert_update_trigger_enabled": bool(trigger and trigger[0] != "D"),
        "insert_update_trigger_definition": trigger[1] if trigger else None,
        "search_vector_gin_index_present": bool(has_gin_index),
        "lexical_join_path": (
            "documents -> document_versions -> document_chunks, with tenant and "
            "accessible data_source filters"
        ),
        "diagnostic_sql_read_only": True,
    }


def _baseline_diagnostic() -> tuple[dict, dict]:
    baseline_cases = json.loads(
        BASELINE_CASES_FILE.read_text(encoding="utf-8")
    )
    baseline_case = next(
        case for case in baseline_cases if case["case_id"] == "banking-001"
    )
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        baseline_trace = _case_diagnostic(db, baseline_case, corpus=None)
        configuration = _read_search_configuration(db)
        return baseline_trace, configuration
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _development_diagnostics(cases: list[dict]) -> tuple[list[dict], bool]:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)
    try:
        corpus = seed_development_corpus(db)
        traces = [
            _case_diagnostic(db, case, corpus=corpus)
            for case in cases
        ]
    finally:
        db.close()
        transaction.rollback()
        connection.close()

    with SessionLocal() as cleanup_db:
        remaining = cleanup_db.scalars(
            text("SELECT id FROM tenants WHERE id = ANY(:tenant_ids)"),
            {"tenant_ids": DEVELOPMENT_TENANT_IDS},
        ).all()
    cleanup_verified = not remaining
    if not cleanup_verified:
        raise RuntimeError("Development synthetic rows remained after rollback")
    return traces, cleanup_verified


def main() -> None:
    baseline_trace, search_configuration = _baseline_diagnostic()
    development_cases = json.loads(
        DEVELOPMENT_CASES_FILE.read_text(encoding="utf-8")
    )
    development_traces, cleanup_verified = _development_diagnostics(
        development_cases
    )

    report = {
        "experiment": "lexical-development-diagnostics-v1",
        "scope_note": (
            "This report is independent of the baseline and held-out reports. "
            "It does not modify either benchmark or production retrieval code."
        ),
        "pipeline_configuration": search_configuration,
        "baseline_success_comparison": baseline_trace,
        "development_case_count": len(development_traces),
        "development_cases": development_traces,
        "synthetic_cleanup_verified": cleanup_verified,
        "synthetic_document_count": len(DEVELOPMENT_DOCUMENTS),
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("Baseline reference")
    print(
        f"{baseline_trace['case_id']}: direct chunks="
        f"{baseline_trace['expected_documents'][0]['direct_matching_chunks']}, "
        f"service hit={baseline_trace['service_returned_expected'][0]}"
    )
    print("Development diagnostics")
    for trace in development_traces:
        detail = trace["expected_documents"][0]
        print(
            f"{trace['case_id']}: tsquery={trace['query_tsquery']}; "
            f"chunks={detail['chunk_count']}; "
            f"direct={detail['direct_matching_chunks']}; "
            f"service_hit={trace['service_returned_expected'][0]}; "
            f"access={trace['expected_access']}"
        )
    print(f"Synthetic cleanup verified: {cleanup_verified}")
    print(f"Report saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()