
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_k: float
    reciprocal_rank_at_k: float
    relevant_retrieved: int
    relevant_expected: int


def _is_valid_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    try:
        UUID(value)
    except (TypeError, ValueError):
        return False

    return True


def validate_evaluation_cases(cases: Any) -> list[str]:
    """Validate the heuristic JSON structure used by the retrieval evaluation runner."""
    errors: list[str] = []

    if not isinstance(cases, list) or not cases:
        return ["Evaluation dataset must be a non-empty list of cases."]

    seen_case_ids: set[str] = set()

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"Case {index}: each entry must be an object.")
            continue

        case_id = case.get("case_id")
        case_label = str(case_id) if case_id is not None else f"case {index}"

        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{case_label}: case_id is required and non-empty.")
        elif case_id in seen_case_ids:
            errors.append(f"{case_label}: case_id must be unique.")
        else:
            seen_case_ids.add(case_id)

        for field_name in ("tenant_id", "user_id"):
            value = case.get(field_name)
            if not _is_valid_uuid(value):
                errors.append(
                    f"{case_label}: {field_name} must be a valid UUID."
                )

        query = case.get("query")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"{case_label}: query must be a non-empty string.")

        expected_document_ids = case.get("expected_document_ids")
        if not isinstance(expected_document_ids, list) or not expected_document_ids:
            errors.append(
                f"{case_label}: expected_document_ids must be a non-empty list."
            )
        else:
            normalized_ids: list[str] = []
            for document_id in expected_document_ids:
                if not _is_valid_uuid(document_id):
                    errors.append(
                        f"{case_label}: expected_document_ids must contain valid UUID strings."
                    )
                    continue
                normalized_ids.append(str(UUID(document_id)))

            if len(set(normalized_ids)) != len(normalized_ids):
                errors.append(
                    f"{case_label}: expected_document_ids must contain unique UUID values."
                )

    return errors


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