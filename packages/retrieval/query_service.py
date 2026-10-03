from uuid import UUID

from packages.llm.citation_validator import CitationValidator
from packages.llm.embeddings import EmbeddingProvider
from packages.llm.generation import (
    AnswerGenerator,
    GeneratedAnswer,
)
from packages.retrieval import evidence
from packages.retrieval.evidence_assembler import EvidenceAssembler
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.query_decomposition import SubQuery
from packages.retrieval.reranker import Reranker
from packages.retrieval.rrf import ReciprocalRankFusion
from sqlalchemy.orm import Session
from packages.retrieval.vector_search import VectorSearchService

class QueryService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider,
        reranker: Reranker,
        answer_generator: AnswerGenerator,
        citation_validator: CitationValidator,
        query_decomposer,
    ) -> None:

        self._db = db

        self._query_decomposer = query_decomposer

        self._citation_validator = citation_validator

        self._hybrid_search = HybridSearchService(
            vector_search=VectorSearchService(
                db=db,
                embedding_provider=embedding_provider,
            ),
            lexical_search=LexicalSearchService(
                db=db,
            ),
            graph_search=GraphSearchService(),
            reranker=reranker,
            rrf=ReciprocalRankFusion(),
        )

        self._evidence_assembler = EvidenceAssembler()

        self._answer_generator = answer_generator

    def answer(
        self,
        tenant_id: UUID,
        query: str,
        user_id: UUID | None = None,
        evidence_limit: int = 5,
    ) -> GeneratedAnswer:
        
        decomposed = self._query_decomposer.decompose(query)

        candidates = self._retrieve_for_subqueries(
            tenant_id,
            decomposed.sub_queries,
            user_id,
        )

        candidates = self._select_candidates(
            candidates,
        )

        evidence = self._evidence_assembler.assemble(
            candidates,
            limit=evidence_limit,
        )

        if not evidence:
            return GeneratedAnswer(
                answer=(
                    "I could not find relevant information to "
                    "answer this question."
                ),
                evidence=[],
                grounded=False,
            )

        generated = self._answer_generator.generate(
            query=query,
            evidence=evidence,
        )

        validation = self._citation_validator.validate(
            generated.answer,
            generated.evidence,
        )

        if not validation.is_valid:
            return GeneratedAnswer(
                answer=(
                    "I found relevant information, but I could not "
                    "produce a reliably sourced answer from it."
                ),
                evidence=evidence,
                grounded=False,
            )

        return generated

    def _retrieve_for_subqueries(
        self,
        tenant_id: UUID,
        sub_queries: list[SubQuery],
        user_id: UUID | None = None,
    ) -> list[dict]:
        candidates: list[dict] = []

        for sub_query in sub_queries:
            results = self._hybrid_search.search(
                db=self._db,
                tenant_id=tenant_id,
                user_id=user_id,
                query=sub_query.query,
                limit=20,
            )

            for result in results:
                enriched = dict(result)
                enriched["sub_query"] = sub_query.query
                enriched["purpose"] = sub_query.purpose
                candidates.append(enriched)

        return candidates

    def _deduplicate_candidates(
        self,
        candidates: list[dict],
    ) -> list[dict]:
        by_chunk_id: dict = {}

        for candidate in candidates:
            chunk_id = candidate["chunk_id"]

            existing = by_chunk_id.get(chunk_id)

            if existing is None:
                by_chunk_id[chunk_id] = candidate
                continue

            if candidate["rerank_score"] > existing["rerank_score"]:
                by_chunk_id[chunk_id] = candidate

        return list(by_chunk_id.values())

    def _select_candidates(
        self,
        candidates: list[dict],
        per_sub_query: int = 3,
    ) -> list[dict]:
        selected: list[dict] = []

        groups: dict[str, list[dict]] = {}

        for candidate in candidates:
            query = candidate["sub_query"]
            groups.setdefault(query, []).append(candidate)

        for group in groups.values():
            group.sort(
                key=lambda item: item["rerank_score"],
                reverse=True,
            )

            selected.extend(
                group[:per_sub_query]
            )

        return self._deduplicate_candidates(selected)

    def should_decompose(query: str) -> bool:
        return (
            query.lower().count(" and ") > 0
            or query.count("?") > 1
        )