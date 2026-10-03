
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_k: float
    reciprocal_rank_at_k: float
    relevant_retrieved: int
    relevant_expected: int


def evaluate_ranked_results(
    retrieved_document_ids: Sequence[str],
    expected_document_ids: set[str],
    k: int = 5,
) -> RetrievalMetrics:
    """Evaluate ranked document IDs against known relevant document IDs."""
    if k < 1:
        raise ValueError("k must be at least 1")

    if not expected_document_ids:
        raise ValueError("expected_document_ids must not be empty")

    # Count each document only once, preserving its first rank.
    ranked_unique: list[str] = []
    seen: set[str] = set()

    for document_id in retrieved_document_ids:
        if document_id not in seen:
            ranked_unique.append(document_id)
            seen.add(document_id)

    top_k = ranked_unique[:k]
    relevant_retrieved = len(set(top_k) & expected_document_ids)

    reciprocal_rank = 0.0
    for rank, document_id in enumerate(top_k, start=1):
        if document_id in expected_document_ids:
            reciprocal_rank = 1.0 / rank
            break

    return RetrievalMetrics(
        recall_at_k=relevant_retrieved / len(expected_document_ids),
        reciprocal_rank_at_k=reciprocal_rank,
        relevant_retrieved=relevant_retrieved,
        relevant_expected=len(expected_document_ids),
    )


def average_metrics(
    results: Sequence[RetrievalMetrics],
) -> dict[str, float]:
    """Macro-average metrics across evaluation questions."""
    if not results:
        raise ValueError("At least one evaluation result is required")

    count = len(results)

    return {
        "recall_at_k": sum(r.recall_at_k for r in results) / count,
        "mrr_at_k": sum(r.reciprocal_rank_at_k for r in results) / count,
        "question_count": float(count),
    }