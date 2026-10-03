# tests/unit/test_lexical_search.py

from uuid import uuid4

import pytest

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
