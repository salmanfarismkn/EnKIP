from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from packages.retrieval.lexical_search import LexicalSearchService


router = APIRouter(
    prefix="/tenants/{tenant_id}/search",
    tags=["search"],
)


@router.post("/lexical", response_model=SearchResponse)
def lexical_search(
    tenant_id: UUID,
    request: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    service = LexicalSearchService(db)

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