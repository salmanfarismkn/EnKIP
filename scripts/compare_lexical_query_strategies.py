"""Compare PostgreSQL lexical query strategies on synthetic dev data only."""

import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from packages.domain.database import SessionLocal, engine
from packages.domain.models import Document
from packages.permissions.service import PermissionService
from packages.retrieval.evaluation import (
    average_metrics,
    evaluate_ranked_results,
)
from packages.retrieval.lexical_search import LexicalSearchService
from lexical_dev_corpus import (
    DEVELOPMENT_DOCUMENTS,
    TENANT_ID,
    DevelopmentCorpus,
    seed_development_corpus,
)


DEVELOPMENT_CASES_FILE = Path("tests/evaluation/lexical_development_cases.json")
REPORT_FILE = Path("reports/lexical_matched_configuration_comparison.json")
K = 5

QUERY_STRATEGIES = {
    "websearch_english": {
        "configuration": "english",
        "vector_column": "english_vector",
        "query_function": "websearch_to_tsquery",
    },
    "plainto_english": {
        "configuration": "english",
        "vector_column": "english_vector",
        "query_function": "plainto_tsquery",
    },
    "websearch_simple": {
        "configuration": "simple",
        "vector_column": "simple_vector",
        "query_function": "websearch_to_tsquery",
    },
    "plainto_simple": {
        "configuration": "simple",
        "vector_column": "simple_vector",
        "query_function": "plainto_tsquery",
    },
}


def _create_temporary_vectors(db: Session) -> None:
    document_ids = [str(document["id"]) for document in DEVELOPMENT_DOCUMENTS]
    db.execute(
        text("""
            CREATE TEMPORARY TABLE lexical_dev_vectors ON COMMIT DROP AS
            SELECT
                c.id AS chunk_id,
                c.tenant_id,
                v.document_id,
                d.data_source_id,
                c.chunk_index,
                c.text,
                to_tsvector('english', coalesce(c.text, '')) AS english_vector,
                to_tsvector('simple', coalesce(c.text, '')) AS simple_vector
            FROM document_chunks c
            JOIN document_versions v ON v.id = c.document_version_id
            JOIN documents d ON d.id = v.document_id
            WHERE d.id IN :document_ids
        """).bindparams(bindparam("document_ids", expanding=True)),
        {"document_ids": document_ids},
    )


def _ranked_matches(
    db: Session,
    strategy_name: str,
    query: str,
    tenant_id: UUID,
    allowed_sources: set[UUID],
) -> tuple[str, list[dict]]:
    strategy = QUERY_STRATEGIES[strategy_name]
    config = strategy["configuration"]
    vector_column = strategy["vector_column"]
    query_function = strategy["query_function"]
    query_sql = f"{query_function}('{config}', :query)"
    query_text = db.execute(
        text(f"SELECT {query_sql}::text"),
        {"query": query},
    ).scalar_one()
    if not allowed_sources:
        return str(query_text), []

    statement = text(f"""
        SELECT chunk_id, document_id,
               ts_rank_cd({vector_column}, {query_sql}) AS rank
        FROM lexical_dev_vectors
        WHERE tenant_id = :tenant_id
          AND data_source_id IN :allowed_sources
          AND {vector_column} @@ {query_sql}
        ORDER BY rank DESC
        LIMIT :limit
    """).bindparams(
        bindparam("allowed_sources", expanding=True)
    )
    rows = db.execute(
        statement,
        {
            "query": query,
            "tenant_id": tenant_id,
            "allowed_sources": sorted(allowed_sources, key=str),
            "limit": K,
        },
    ).all()
    return str(query_text), [
        {
            "chunk_id": str(row[0]),
            "document_id": str(row[1]),
            "rank": float(row[2]),
        }
        for row in rows
    ]


def _whole_document_match(
    db: Session,
    strategy_name: str,
    query: str,
    tenant_id: UUID,
    document_id: UUID,
    allowed_sources: set[UUID],
) -> dict:
    strategy = QUERY_STRATEGIES[strategy_name]
    config = strategy["configuration"]
    vector_column = strategy["vector_column"]
    query_function = strategy["query_function"]
    query_sql = f"{query_function}('{config}', :query)"
    if not allowed_sources:
        return {
            "individually_matching_chunk_ids": [],
            "combined_text_match_for_diagnostic_only": False,
        }

    matching_chunk_ids = db.execute(
        text(f"""
            SELECT chunk_id
            FROM lexical_dev_vectors
            WHERE tenant_id = :tenant_id
              AND document_id = :document_id
              AND data_source_id IN :allowed_sources
              AND {vector_column} @@ {query_sql}
            ORDER BY chunk_index
        """).bindparams(bindparam("allowed_sources", expanding=True)),
        {
            "query": query,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "allowed_sources": sorted(allowed_sources, key=str),
        },
    ).scalars().all()
    combined_match = db.execute(
        text(f"""
            SELECT to_tsvector('{config}', string_agg(text, ' '))
                   @@ {query_sql}
            FROM lexical_dev_vectors
            WHERE tenant_id = :tenant_id
              AND document_id = :document_id
              AND data_source_id IN :allowed_sources
        """).bindparams(bindparam("allowed_sources", expanding=True)),
        {
            "query": query,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "allowed_sources": sorted(allowed_sources, key=str),
        },
    ).scalar_one()
    return {
        "individually_matching_chunk_ids": [
            str(chunk_id) for chunk_id in matching_chunk_ids
        ],
        "combined_text_match_for_diagnostic_only": bool(combined_match),
    }


def _development_run(cases: list[dict]) -> dict:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)
    corpus: DevelopmentCorpus | None = None
    metrics_by_strategy = defaultdict(list)
    empty_result_cases = {name: [] for name in QUERY_STRATEGIES}
    authorized_empty_result_cases = {name: [] for name in QUERY_STRATEGIES}
    case_failures = {name: [] for name in QUERY_STRATEGIES}
    permission_violations = []
    case_reports = []

    try:
        corpus = seed_development_corpus(db)
        _create_temporary_vectors(db)
        permission_service = PermissionService()
        production_lexical = LexicalSearchService(db=db)

        for case in cases:
            tenant_id = UUID(case["tenant_id"])
            user_id = UUID(case["user_id"])
            query = case["query"]
            expected_ids = {
                UUID(value) for value in case["expected_document_ids"]
            }
            allowed_sources = permission_service.get_accessible_data_source_ids(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            actual_expected_access = all(
                document_id in corpus.document_context
                and corpus.document_context[document_id][0] == tenant_id
                and corpus.document_context[document_id][1] in allowed_sources
                for document_id in expected_ids
            )
            if actual_expected_access != case["expected_access"]:
                raise AssertionError(
                    f"Access label mismatch for {case['case_id']}"
                )

            strategy_reports = {}
            for strategy_name in QUERY_STRATEGIES:
                query_text, matches = _ranked_matches(
                    db=db,
                    strategy_name=strategy_name,
                    query=query,
                    tenant_id=tenant_id,
                    allowed_sources=allowed_sources,
                )
                chunk_ids = [match["chunk_id"] for match in matches]
                ranked_document_ids = list(
                    dict.fromkeys(match["document_id"] for match in matches)
                )
                ranked_document_set = {
                    UUID(document_id) for document_id in ranked_document_ids
                }

                accessible_document_ids = {
                    document_id
                    for document_id, context in corpus.document_context.items()
                    if context[0] == tenant_id and context[1] in allowed_sources
                }
                leaked_ids = sorted(
                    str(document_id)
                    for document_id in ranked_document_set
                    if document_id not in accessible_document_ids
                )
                if leaked_ids:
                    permission_violations.append(
                        {
                            "case_id": case["case_id"],
                            "strategy": strategy_name,
                            "document_ids": leaked_ids,
                        }
                    )

                returned_expected = sorted(
                    str(document_id)
                    for document_id in ranked_document_set & expected_ids
                )
                if case["expected_access"]:
                    metrics = evaluate_ranked_results(
                        retrieved_document_ids=ranked_document_ids,
                        expected_document_ids={str(value) for value in expected_ids},
                        k=K,
                    )
                    metrics_by_strategy[strategy_name].append(metrics)
                    missing_ids = sorted(
                        str(document_id)
                        for document_id in expected_ids - ranked_document_set
                    )
                    if missing_ids:
                        case_failures[strategy_name].append(
                            {
                                "case_id": case["case_id"],
                                "missing_expected_document_ids": missing_ids,
                            }
                        )
                else:
                    metrics = None
                    missing_ids = []
                    if returned_expected:
                        permission_violations.append(
                            {
                                "case_id": case["case_id"],
                                "strategy": strategy_name,
                                "document_ids": returned_expected,
                                "reason": "unauthorized_expected_document_returned",
                            }
                        )

                if not matches:
                    empty_result_cases[strategy_name].append(case["case_id"])
                    if case["expected_access"]:
                        authorized_empty_result_cases[strategy_name].append(
                            case["case_id"]
                        )

                production_ids = [
                    str(result["document_id"])
                    for result in production_lexical.search(
                        db=db,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        query=query,
                        limit=K,
                    )
                ]
                production_unique_ids = list(dict.fromkeys(production_ids))
                if strategy_name == "websearch_english" and (
                    production_unique_ids != ranked_document_ids
                ):
                    raise AssertionError(
                        f"Development baseline differs from production lexical "
                        f"service for {case['case_id']}"
                    )

                strategy_reports[strategy_name] = {
                    "generated_tsquery": query_text,
                    "matched_chunk_ids": chunk_ids,
                    "matched_document_ids": ranked_document_ids,
                    "expected_document_ids_returned": returned_expected,
                    "expected_document_ids_missing": missing_ids,
                    "metrics": asdict(metrics) if metrics is not None else None,
                    "production_baseline_document_ids": production_unique_ids,
                }

                if case.get("case_kind", "").startswith("multi_chunk_"):
                    expected_document_id = next(iter(expected_ids))
                    strategy_reports[strategy_name]["chunk_boundary_analysis"] = (
                        _whole_document_match(
                            db=db,
                            strategy_name=strategy_name,
                            query=query,
                            tenant_id=tenant_id,
                            document_id=expected_document_id,
                            allowed_sources=allowed_sources,
                        )
                    )

            case_reports.append(
                {
                    "case_id": case["case_id"],
                    "case_kind": case["case_kind"],
                    "query": query,
                    "tenant_id": case["tenant_id"],
                    "user_id": case["user_id"],
                    "expected_document_ids": sorted(str(value) for value in expected_ids),
                    "expected_access": case["expected_access"],
                    "accessible_data_source_ids": sorted(
                        str(source_id) for source_id in allowed_sources
                    ),
                    "strategies": strategy_reports,
                }
            )
    finally:
        db.close()
        transaction.rollback()
        connection.close()

    with SessionLocal() as cleanup_db:
        remaining = cleanup_db.execute(
            select(Document.id).where(
                Document.id.in_(
                    [document["id"] for document in DEVELOPMENT_DOCUMENTS]
                )
            )
        ).all()
    cleanup_verified = not remaining
    if not cleanup_verified:
        raise RuntimeError("Development corpus remained after rollback")

    return {
        "k": K,
        "case_count": len(case_reports),
        "quality_case_count": sum(
            bool(case["expected_access"]) for case in case_reports
        ),
        "aggregate": {
            strategy: average_metrics(metrics)
            for strategy, metrics in metrics_by_strategy.items()
        },
        "per_case_failures": case_failures,
        "empty_result_cases": empty_result_cases,
        "authorized_empty_result_cases": authorized_empty_result_cases,
        "permission_violations": permission_violations,
        "cleanup_verified": cleanup_verified,
        "cases": case_reports,
    }


def main() -> None:
    cases = json.loads(DEVELOPMENT_CASES_FILE.read_text(encoding="utf-8"))
    result = _development_run(cases)
    report = {
        "experiment": "postgresql-lexical-query-strategies-v1",
        "scope": (
            "Development-only matched vector/query configuration comparison. No production "
            "retrieval behavior or protected baseline/held-out artifacts changed."
        ),
        "query_strategies": [
            "websearch_english",
            "plainto_english",
            "websearch_simple",
            "plainto_simple",
        ],
        "index_configurations": {
            "english_vector": "to_tsvector('english', chunk_text)",
            "simple_vector": "to_tsvector('simple', chunk_text)",
        },
        "strategy_configurations": {
            "websearch_english": "websearch_to_tsquery('english', query)",
            "plainto_english": "plainto_tsquery('english', query)",
            "websearch_simple": "websearch_to_tsquery('simple', query)",
            "plainto_simple": "plainto_tsquery('simple', query)",
        },
        "configuration_comparison_note": (
            "Every strategy uses vectors and a query built with the same "
            "configuration. Both temporary vectors are computed from the same "
            "synthetic chunk text; production DocumentChunk.search_vector is "
            "not changed."
        ),
        "ranking_and_access_note": (
            "All strategies use the same source rows, tenant/user, actual "
            "PermissionService source allow-list, ts_rank_cd, and top-5 chunk "
            "limit. Recall/MRR macro averages include authorized expected cases "
            "only; unauthorized cases are evaluated as permission checks."
        ),
        "chunk_boundary_note": (
            "Combined-text matches are diagnostics only. Retrieval remains "
            "per chunk; no concatenated text is indexed or searched."
        ),
        **result,
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("Lexical query strategy comparison (authorized cases only)")
    for strategy, metrics in report["aggregate"].items():
        print(
            f"{strategy:20} Recall@{K}={metrics['recall_at_k']:.3f}  "
            f"MRR@{K}={metrics['mrr_at_k']:.3f}  "
            f"cases={int(metrics['question_count'])}"
        )
        print(
            f"  failures={len(report['per_case_failures'][strategy])}; "
            f"authorized_empty={report['authorized_empty_result_cases'][strategy]}"
        )
    print(f"Permission violations: {len(report['permission_violations'])}")
    print(f"Synthetic cleanup verified: {report['cleanup_verified']}")
    print(f"Report saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()