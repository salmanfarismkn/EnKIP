
import json
from pathlib import Path

import pytest

from packages.retrieval.evaluation import (
    average_metrics,
    evaluate_ranked_results,
    validate_evaluation_cases,
)


def test_recall_and_mrr_for_ranked_results():
    metrics = evaluate_ranked_results(
        retrieved_document_ids=["doc-x", "doc-b", "doc-a"],
        expected_document_ids={"doc-a", "doc-b"},
        k=3,
    )

    assert metrics.recall_at_k == 1.0
    assert metrics.reciprocal_rank_at_k == 0.5
    assert metrics.relevant_retrieved == 2


def test_no_relevant_results():
    metrics = evaluate_ranked_results(
        retrieved_document_ids=["doc-x", "doc-y"],
        expected_document_ids={"doc-a"},
        k=5,
    )

    assert metrics.recall_at_k == 0.0
    assert metrics.reciprocal_rank_at_k == 0.0


def test_duplicate_documents_count_once():
    metrics = evaluate_ranked_results(
        retrieved_document_ids=["doc-a", "doc-a", "doc-b"],
        expected_document_ids={"doc-a", "doc-b"},
        k=3,
    )

    assert metrics.recall_at_k == 1.0
    assert metrics.reciprocal_rank_at_k == 1.0


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError):
        evaluate_ranked_results(["doc-a"], {"doc-a"}, k=0)


def test_empty_expected_set_is_rejected():
    with pytest.raises(ValueError):
        evaluate_ranked_results(["doc-a"], set())


def test_average_metrics():
    first = evaluate_ranked_results(["doc-a"], {"doc-a"}, k=5)
    second = evaluate_ranked_results(["doc-x"], {"doc-a"}, k=5)

    averages = average_metrics([first, second])

    assert averages["recall_at_k"] == 0.5
    assert averages["mrr_at_k"] == 0.5
    assert averages["question_count"] == 2.0


def test_validate_evaluation_cases_accepts_well_formed_dataset() -> None:
    cases_path = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "retrieval_cases.json"
    )
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    errors = validate_evaluation_cases(cases)

    assert not errors
    assert len(cases) >= 20


def test_validate_evaluation_cases_rejects_invalid_case() -> None:
    cases = [
        {
            "case_id": "banking-001",
            "tenant_id": "not-a-uuid",
            "user_id": "72154ff0-9af7-4a91-9522-e63b5b9de18e",
            "query": "",
            "expected_document_ids": [],
        }
    ]

    errors = validate_evaluation_cases(cases)

    assert any("tenant_id" in error.lower() for error in errors)
    assert any("query" in error.lower() for error in errors)
    assert any("expected_document_ids" in error.lower() for error in errors)