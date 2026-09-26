from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    text: str
    section_title: str | None
    page_number: int | None
    similarity: float


class SearchResponse(BaseModel):
    results: list[SearchResult]