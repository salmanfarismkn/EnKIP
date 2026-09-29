from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from apps.api.config import settings
from packages.llm.ollama_embeddings import OllamaEmbeddingProvider
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
from packages.retrieval.factory import get_reranker

router = APIRouter(
    prefix="/tenants/{tenant_id}/search",
    tags=["search"],
)


@router.post("", response_model=SearchResponse)
def search(
    tenant_id: UUID,
    request: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    provider = OllamaEmbeddingProvider(
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        base_url=settings.ollama_base_url,
    )

    reranker = get_reranker()

    service = HybridSearchService(
        db=db,
        embedding_provider=provider,
        reranker=reranker,
    )

    results = service.search(
        tenant_id=tenant_id,
        query=request.query,
        limit=request.limit,
    )

    return SearchResponse(
        results=[
            SearchResult(
                chunk_id=result["chunk_id"],
                document_id=result["document_id"],
                document_title=result["document_title"],
                text=result["text"],
                section_title=result["section_title"],
                page_number=result["page_number"],
                retrieval_score=result["score"],
                rerank_score=result["rerank_score"],
            )
            for result in results
        ]
    )