from uuid import uuid4

from packages.retrieval.rrf import ReciprocalRankFusion


def test_rrf_combines_ranks() -> None:
    chunk_a = uuid4()
    chunk_b = uuid4()
    chunk_c = uuid4()

    fusion = ReciprocalRankFusion(k=60)

    semantic = [
        {"chunk_id": chunk_a},
        {"chunk_id": chunk_b},
        {"chunk_id": chunk_c},
    ]

    lexical = [
        {"chunk_id": chunk_c},
        {"chunk_id": chunk_a},
        {"chunk_id": uuid4()},
    ]

    results = fusion.fuse(
        [semantic, lexical]
    )

    assert results[0]["chunk_id"] == chunk_a

def test_rrf_empty_results() -> None:
    fusion = ReciprocalRankFusion()

    assert fusion.fuse([[], []]) == []

def test_rrf_rejects_invalid_k() -> None:
    try:
        ReciprocalRankFusion(k=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")