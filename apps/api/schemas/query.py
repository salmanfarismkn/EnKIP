from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    evidence_limit: int = Field(
        default=5,
        ge=1,
        le=10,
    )


class CitationResponse(BaseModel):
    source_number: int
    chunk_id: str
    document_id: str
    document_title: str
    section_title: str | None
    page_number: int | None


class QueryResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[CitationResponse]