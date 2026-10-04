# tests/unit/test_lexical_search.py

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from packages.domain.database import SessionLocal
from packages.retrieval.lexical_search import (
    LexicalSearchService,
)


def test_empty_query_raises_value_error() -> None:
    service = LexicalSearchService(db=None)

    with pytest.raises(
        ValueError,
        match="Query must not be empty",
    ):
        service.search(
            db=None,
            tenant_id=uuid4(),
            user_id=uuid4(),
            query="",
            limit=10,
        )


def test_whitespace_query_raises_value_error() -> None:
    service = LexicalSearchService(db=None)

    with pytest.raises(
        ValueError,
        match="Query must not be empty",
    ):
        service.search(
            db=None,
            tenant_id=uuid4(),
            user_id=uuid4(),
            query="   ",
            limit=10,
        )


def test_zero_limit_raises_value_error() -> None:
    service = LexicalSearchService(db=None)

    with pytest.raises(
        ValueError,
        match="Limit must be positive",
    ):
        service.search(
            db=None,
            tenant_id=uuid4(),
            user_id=uuid4(),
            query="redis",
            limit=0,
        )


def test_negative_limit_raises_value_error() -> None:
    service = LexicalSearchService(db=None)

    with pytest.raises(
        ValueError,
        match="Limit must be positive",
    ):
        service.search(
            db=None,
            tenant_id=uuid4(),
            user_id=uuid4(),
            query="redis",
            limit=-1,
        )


def test_retrieval_cases_match_expected_documents_lexically() -> None:
    cases = json.loads(
        Path("tests/evaluation/retrieval_cases.json")
        .read_text(encoding="utf-8")
    )

    with SessionLocal() as db:
        service = LexicalSearchService(db=db)
        for case in cases:
            case_id = case["case_id"]
            tenant_id = UUID(case["tenant_id"])
            user_id = UUID(case["user_id"])
            expected_ids = [UUID(value) for value in case["expected_document_ids"]]
            query = case["query"]

            results = service.search(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                query=query,
                limit=1000,
            )
            matched_ids = {result["document_id"] for result in results}

            assert set(expected_ids).issubset(matched_ids), (
                f"Evaluation case {case_id} expected documents are not "
                f"retrievable for its tenant and user: {query}"
            )
