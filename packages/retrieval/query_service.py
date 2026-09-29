from uuid import UUID

from packages.llm.embeddings import EmbeddingProvider
from packages.llm.generation import (
    AnswerGenerator,
    GeneratedAnswer,
)
from packages.retrieval.evidence_assembler import EvidenceAssembler
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.reranker import Reranker
from packages.retrieval.rrf import ReciprocalRankFusion
from sqlalchemy.orm import Session


class QueryService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider,
        reranker: Reranker,
        answer_generator: AnswerGenerator,
    ) -> None:
        self._hybrid_search = HybridSearchService(
            db=db,
            embedding_provider=embedding_provider,
            reranker=reranker,
            rrf=ReciprocalRankFusion(),
        )

        self._evidence_assembler = EvidenceAssembler()
        self._answer_generator = answer_generator

    def answer(
        self,
        tenant_id: UUID,
        query: str,
        evidence_limit: int = 5,
    ) -> GeneratedAnswer:
        candidates = self._hybrid_search.search(
            tenant_id=tenant_id,
            query=query,
            limit=max(evidence_limit * 3, 20),
        )

        evidence = self._evidence_assembler.assemble(
            results=candidates,
            limit=evidence_limit,
        )

        return self._answer_generator.generate(
            query=query,
            evidence=evidence,
        )