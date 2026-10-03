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
        vector_search,
        lexical_search,
        graph_search,
        reranker,
        rrf,
    ) -> None:
        self._vector_search = vector_search
        self._lexical_search = lexical_search
        self._graph_search = graph_search
        self._reranker = reranker
        self._rrf = rrf

    def search(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
        user_id: UUID | None = None,
        limit: int = 10,
    ) -> list[dict]:
        if not query.strip():
            raise ValueError("Query must not be empty")

        if limit <= 0:
            raise ValueError("Limit must be positive")

        candidate_limit = max(limit * 3, 20)

        semantic_results = self._vector_search.search(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            limit=candidate_limit,
        )

        lexical_results = self._lexical_search.search(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            limit=candidate_limit,
        )

        graph_results = self._graph_search.search(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            limit=candidate_limit,
        )

        fused_results = self._rrf.fuse(
            [
                semantic_results,
                lexical_results,
            ]
        )

        candidates = self._merge_candidates(
            fused_results,
            graph_results,
        )

        return self._reranker.rerank(
            query,
            candidates,
        )[:limit]

    def _merge_candidates(
        self,
        fused_results: list[dict],
        graph_results: list[dict],
    ) -> list[dict]:
        candidates = {
            result["chunk_id"]: dict(result)
            for result in fused_results
        }

        for graph_result in graph_results:
            chunk_id = graph_result["chunk_id"]
            candidate = candidates.get(chunk_id)

            if candidate is None:
                candidates[chunk_id] = dict(graph_result)
                continue

            relationships = list(
                candidate.get("graph_relationships", [])
            )
            for relationship in graph_result.get(
                "graph_relationships", []
            ):
                if relationship not in relationships:
                    relationships.append(relationship)

            candidate["graph_relationships"] = relationships

        return list(candidates.values())