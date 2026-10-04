"""Run the isolated, synthetic held-out retrieval benchmark."""

import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from uuid import UUID

from sqlalchemy.orm import Session

from apps.api.config import settings
from packages.domain.database import engine
from packages.llm.ollama_embeddings import OllamaEmbeddingProvider
from packages.retrieval.evaluation import (
    average_metrics,
    evaluate_ranked_results,
    validate_evaluation_cases,
)
from packages.retrieval.factory import get_reranker
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
from packages.retrieval.vector_search import VectorSearchService
from heldout_corpus import (
    SYNTHETIC_DOCUMENTS,
    SeededCorpus,
    seed_heldout_corpus,
)


EVALUATION_FILE = Path("tests/evaluation/heldout_retrieval_cases.json")
REPORT_FILE = Path("reports/heldout_retrieval_evaluation_report.json")
K = 5
STRATEGIES = ("vector", "lexical", "hybrid", "graph_assisted_hybrid")


class NoGraphSearch:
    def search(self, **kwargs) -> list[dict]:
        return []


def document_ids(results: list[dict]) -> list[str]:
    unique_ids = []
    seen = set()
    for result in results:
        document_id = result.get("document_id")
        if document_id is not None and str(document_id) not in seen:
            seen.add(str(document_id))
            unique_ids.append(str(document_id))
    return unique_ids


def _validate_case_access(case: dict, corpus: SeededCorpus) -> tuple[set[UUID], set[UUID]]:
    tenant_id = UUID(case["tenant_id"])
    user_id = UUID(case["user_id"])
    allowed_sources = corpus.allowed_sources_by_user.get(user_id, set())
    expected_ids = {UUID(value) for value in case["expected_document_ids"]}
    forbidden_ids = {
        UUID(value) for value in case.get("forbidden_document_ids", [])
    }

    for document_id in expected_ids:
        context = corpus.document_context.get(document_id)
        if context is None or context[0] != tenant_id or context[1] not in allowed_sources:
            raise ValueError(
                f"Expected document {document_id} is not accessible in {case['case_id']}"
            )

    for document_id in forbidden_ids:
        context = corpus.document_context.get(document_id)
        if context is None:
            raise ValueError(
                f"Forbidden document {document_id} is not in the synthetic corpus"
            )
        if context[0] == tenant_id and context[1] in allowed_sources:
            raise ValueError(
                f"Forbidden document {document_id} is accessible in {case['case_id']}"
            )

    return expected_ids, forbidden_ids


def _run_cases(cases: list[dict]) -> dict:
    reranker = get_reranker()
    embedding_provider = OllamaEmbeddingProvider(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        base_url=settings.ollama_base_url,
    )
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)
    metrics_by_strategy = defaultdict(list)
    duration_by_strategy = defaultdict(float)
    case_reports = []
    failures = []
    empty_result_cases = {strategy: [] for strategy in STRATEGIES}
    permission_violations = []

    try:
        seeded = seed_heldout_corpus(db, embedding_provider)
        for case in cases:
            tenant_id = UUID(case["tenant_id"])
            user_id = UUID(case["user_id"])
            expected_ids, forbidden_ids = _validate_case_access(case, seeded)

            vector_search = VectorSearchService(
                db=db,
                embedding_provider=embedding_provider,
            )
            lexical_search = LexicalSearchService(db=db)
            graph_search = GraphSearchService()
            hybrid_only = HybridSearchService(
                vector_search=vector_search,
                lexical_search=lexical_search,
                graph_search=NoGraphSearch(),
                reranker=reranker,
                rrf=ReciprocalRankFusion(),
            )
            graph_assisted = HybridSearchService(
                vector_search=vector_search,
                lexical_search=lexical_search,
                graph_search=graph_search,
                reranker=reranker,
                rrf=ReciprocalRankFusion(),
            )

            searches = {
                "vector": vector_search.search,
                "lexical": lexical_search.search,
                "hybrid": hybrid_only.search,
                "graph_assisted_hybrid": graph_assisted.search,
            }
            strategy_reports = {}

            for strategy, search in searches.items():
                started_at = perf_counter()
                results = search(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=case["query"],
                    limit=K,
                )
                elapsed = perf_counter() - started_at
                duration_by_strategy[strategy] += elapsed
                retrieved_ids = document_ids(results)
                retrieved_set = {UUID(value) for value in retrieved_ids}
                metrics = evaluate_ranked_results(
                    retrieved_document_ids=retrieved_ids,
                    expected_document_ids={str(value) for value in expected_ids},
                    k=K,
                )
                metrics_by_strategy[strategy].append(metrics)

                accessible_ids = {
                    document_id
                    for document_id, context in seeded.document_context.items()
                    if context[0] == tenant_id
                    and context[1]
                    in seeded.allowed_sources_by_user.get(user_id, set())
                }
                violations = sorted(
                    str(document_id)
                    for document_id in retrieved_set - accessible_ids
                )
                if violations:
                    permission_violations.append(
                        {
                            "case_id": case["case_id"],
                            "strategy": strategy,
                            "document_ids": violations,
                        }
                    )

                forbidden_returned = sorted(
                    str(document_id)
                    for document_id in retrieved_set & forbidden_ids
                )
                if forbidden_returned:
                    permission_violations.append(
                        {
                            "case_id": case["case_id"],
                            "strategy": strategy,
                            "document_ids": forbidden_returned,
                            "label": "forbidden_document_returned",
                        }
                    )

                missing_expected = sorted(
                    str(document_id)
                    for document_id in expected_ids - retrieved_set
                )
                if missing_expected:
                    failures.append(
                        {
                            "case_id": case["case_id"],
                            "strategy": strategy,
                            "missing_expected_document_ids": missing_expected,
                        }
                    )
                if not retrieved_ids:
                    empty_result_cases[strategy].append(case["case_id"])

                strategy_reports[strategy] = {
                    "retrieved_document_ids": retrieved_ids,
                    "metrics": asdict(metrics),
                    "missing_expected_document_ids": missing_expected,
                    "permission_violation_document_ids": violations,
                    "forbidden_document_ids_returned": forbidden_returned,
                    "duration_seconds": elapsed,
                }

            case_reports.append(
                {
                    "case_id": case["case_id"],
                    "tenant_id": case["tenant_id"],
                    "user_id": case["user_id"],
                    "query": case["query"],
                    "expected_document_ids": sorted(str(value) for value in expected_ids),
                    "forbidden_document_ids": sorted(str(value) for value in forbidden_ids),
                    "strategies": strategy_reports,
                }
            )
            print(f"Evaluated held-out case: {case['case_id']}")
    finally:
        db.close()
        transaction.rollback()
        connection.close()

    return {
        "aggregate": {
            strategy: average_metrics(values)
            for strategy, values in metrics_by_strategy.items()
        },
        "cases": case_reports,
        "per_case_failures": failures,
        "empty_result_cases": empty_result_cases,
        "permission_violations": permission_violations,
        "duration_seconds_by_strategy": dict(duration_by_strategy),
    }


def main() -> None:
    cases = json.loads(EVALUATION_FILE.read_text(encoding="utf-8"))
    validation_errors = validate_evaluation_cases(cases)
    if validation_errors:
        raise ValueError("\n".join(validation_errors))

    report_results = _run_cases(cases)
    report = {
        "benchmark": "synthetic-heldout-v1",
        "k": K,
        "case_count": len(cases),
        "metrics_note": (
            "Macro-averaged document-level Recall@5 and MRR@5 on static, "
            "manually labeled synthetic cases. No tuning was performed on this set."
        ),
        "environment": {
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
            "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "corpus_documents": len(SYNTHETIC_DOCUMENTS),
            "execution_note": (
                "Synthetic rows are created in a database transaction and rolled back. "
                "Timings are local-environment observations, not production benchmarks."
            ),
        },
        **report_results,
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\nHeld-out retrieval metrics")
    for strategy, metrics in report["aggregate"].items():
        print(
            f"{strategy:24} Recall@{K}={metrics['recall_at_k']:.3f}  "
            f"MRR@{K}={metrics['mrr_at_k']:.3f}"
        )
    print(f"Per-case failures: {len(report['per_case_failures'])}")
    print(f"Permission violations: {len(report['permission_violations'])}")
    print(f"Report saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()