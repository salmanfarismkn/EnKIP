
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from apps.api.config import settings
from packages.domain.database import SessionLocal
from packages.llm.ollama_embeddings import OllamaEmbeddingProvider
from packages.retrieval.evaluation import (
    average_metrics,
    evaluate_ranked_results,
)
from packages.retrieval.factory import get_reranker
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
from packages.retrieval.vector_search import VectorSearchService


EVALUATION_FILE = Path(
    "tests/evaluation/retrieval_cases.json"
)
REPORT_FILE = Path(
    "reports/retrieval_evaluation_report.json"
)
K = 5


class NoGraphSearch:
    """Disable graph candidates to measure hybrid retrieval alone."""

    def search(self, **kwargs) -> list[dict]:
        return []


def document_ids(results: list[dict]) -> list[str]:
    """Return unique document IDs in retrieval rank order."""
    unique_ids: list[str] = []
    seen: set[str] = set()

    for result in results:
        document_id = result.get("document_id")
        if document_id is None:
            continue

        normalized_id = str(document_id)

        if normalized_id not in seen:
            seen.add(normalized_id)
            unique_ids.append(normalized_id)

    return unique_ids


def main() -> None:
    if not EVALUATION_FILE.exists():
        raise FileNotFoundError(
            f"Evaluation dataset not found: {EVALUATION_FILE}"
        )

    cases = json.loads(
        EVALUATION_FILE.read_text(encoding="utf-8")
    )

    if not isinstance(cases, list) or not cases:
        raise ValueError(
            "Evaluation dataset must contain at least one case"
        )

    reranker = get_reranker()

    embedding_provider = OllamaEmbeddingProvider(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        base_url=settings.ollama_base_url,
    )

    per_strategy_metrics = defaultdict(list)
    case_reports = []

    with SessionLocal() as db:
        for case in cases:
            case_id = case["case_id"]
            tenant_id = UUID(case["tenant_id"])
            user_id = UUID(case["user_id"])
            query = case["query"].strip()
            expected_ids = {
                str(UUID(value))
                for value in case["expected_document_ids"]
            }

            if not query:
                raise ValueError(
                    f"Empty query in evaluation case {case_id}"
                )

            if not expected_ids:
                raise ValueError(
                    f"No expected documents in case {case_id}"
                )

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

            # Every strategy uses the same tenant and user.
            results_by_strategy = {
                "vector": vector_search.search(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=query,
                    limit=K,
                ),
                "lexical": lexical_search.search(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=query,
                    limit=K,
                ),
                "hybrid": hybrid_only.search(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=query,
                    limit=K,
                ),
                "graph_assisted_hybrid": graph_assisted.search(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query=query,
                    limit=K,
                ),
            }

            strategy_reports = {}

            for strategy, results in results_by_strategy.items():
                retrieved_ids = document_ids(results)

                metrics = evaluate_ranked_results(
                    retrieved_document_ids=retrieved_ids,
                    expected_document_ids=expected_ids,
                    k=K,
                )

                per_strategy_metrics[strategy].append(metrics)

                strategy_reports[strategy] = {
                    "retrieved_document_ids": retrieved_ids,
                    "metrics": asdict(metrics),
                }

            case_reports.append(
                {
                    "case_id": case_id,
                    "query": query,
                    "expected_document_ids": sorted(expected_ids),
                    "strategies": strategy_reports,
                }
            )

            print(f"Evaluated: {case_id}")

    aggregate = {
        strategy: average_metrics(metrics)
        for strategy, metrics in per_strategy_metrics.items()
    }

    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "k": K,
        "case_count": len(case_reports),
        "metrics_note": (
            "Macro-averaged document-level Recall@K and MRR@K. "
            "Results depend on the manually labeled evaluation set."
        ),
        "aggregate": aggregate,
        "cases": case_reports,
    }

    REPORT_FILE.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nAggregate retrieval metrics")
    for strategy, metrics in aggregate.items():
        print(
            f"{strategy:24} "
            f"Recall@{K}={metrics['recall_at_k']:.3f}  "
            f"MRR@{K}={metrics['mrr_at_k']:.3f}"
        )

    print(f"\nReport saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()