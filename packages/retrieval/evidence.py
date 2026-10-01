from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Evidence:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    text: str
    section_title: str | None
    page_number: int | None
    retrieval_score: float
    rerank_score: float
    graph_relationships: tuple[str, ...] = ()