from functools import lru_cache

from packages.retrieval.local_reranker import (
    LocalCrossEncoderReranker,
)


@lru_cache(maxsize=1)
def get_reranker() -> LocalCrossEncoderReranker:
    return LocalCrossEncoderReranker()