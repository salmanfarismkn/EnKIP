from uuid import UUID

from sqlalchemy.orm import Session
from sympy import limit

from packages.llm.embeddings import EmbeddingProvider
from packages.retrieval import graph_search
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
from packages.retrieval.vector_search import VectorSearchService


from packages.retrieval.reranker import Reranker


class HybridSearchService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider,
        reranker: Reranker,
        graph_search: GraphSearchService,
        rrf: ReciprocalRankFusion | None = None,
    ) -> None:
        self._vector_search = VectorSearchService(
            db=db,
            embedding_provider=embedding_provider,
        )

        self._lexical_search = LexicalSearchService(
            db=db,
        )

        self._graph_search = graph_search

        self._rrf = rrf or ReciprocalRankFusion()

        self._reranker = reranker

    def search(
        self,
        tenant_id: UUID,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        if not query.strip():
            raise ValueError("Query must not be empty")

        if limit <= 0:
            raise ValueError("Limit must be positive")

        candidate_limit = max(limit * 3, 20)

        semantic_results = self._vector_search.search(
            tenant_id=tenant_id,
            query=query,
            limit=candidate_limit,
        )

        lexical_results = self._lexical_search.search(
            tenant_id=tenant_id,
            query=query,
            limit=candidate_limit,
        )

        graph_results = self._graph_search.search(
            tenant_id=tenant_id,
            query=query,
            limit=candidate_limit,
        )

        fused_results = self._rrf.fuse(
            [
                semantic_results,
                lexical_results,
                graph_results,
            ]
        )

        reranked_results = self._reranker.rerank(
            query=query,
            results=fused_results,
        )

        return reranked_results[:limit]