from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.dependencies import get_db
from apps.api.schemas.query import (
    CitationResponse,
    QueryRequest,
    QueryResponse,
)
from packages.llm.citation_validator import CitationValidator
from packages.llm.ollama_embeddings import (
    OllamaEmbeddingProvider,
)
from packages.llm.ollama_generation import (
    OllamaAnswerGenerator,
)
from packages.retrieval.factory import get_reranker
from packages.retrieval.query_service import QueryService
from packages.llm.ollama_decomposition import (
    OllamaQueryDecomposer,
)

router = APIRouter(
    prefix="/tenants/{tenant_id}/query",
    tags=["query"],
)


@router.post("", response_model=QueryResponse)
def query(
    tenant_id: UUID,
    request: QueryRequest,
    db: Session = Depends(get_db),
) -> QueryResponse:
    embedding_provider = OllamaEmbeddingProvider(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        base_url=settings.ollama_base_url,
    )

    reranker = get_reranker()

    answer_generator = OllamaAnswerGenerator(
        model_name=settings.generation_model,
        base_url=settings.ollama_base_url,
    )

    service = QueryService(
        db=db,
        embedding_provider=embedding_provider,
        reranker=reranker,
        answer_generator=answer_generator,
    )

    result = service.answer(
        tenant_id=tenant_id,
        query=request.query,
        evidence_limit=request.evidence_limit,
    )

    citations = [
        CitationResponse(
            source_number=index,
            chunk_id=str(item.chunk_id),
            document_id=str(item.document_id),
            document_title=item.document_title,
            section_title=item.section_title,
            page_number=item.page_number,
        )
        for index, item in enumerate(
            result.evidence,
            start=1,
        )
    ]
    
    query_decomposer = OllamaQueryDecomposer(
        model_name=settings.decomposition_model,
        base_url=settings.ollama_base_url,
    )

    service = QueryService(
        db=db,
        embedding_provider=embedding_provider,
        reranker=reranker,
        answer_generator=answer_generator,
        citation_validator=CitationValidator(),
        query_decomposer=query_decomposer,
    )

    return QueryResponse(
        answer=result.answer,
        grounded=result.grounded,
        citations=citations,
    )