from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.domain.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
)


class LexicalSearchService:
    def __init__(self, db: Session) -> None:
        self._db = db

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

        ts_query = func.websearch_to_tsquery(
            "english",
            query,
        )

        rank = func.ts_rank_cd(
            DocumentChunk.search_vector,
            ts_query,
        )

        statement = (
            select(
                DocumentChunk.id,
                DocumentChunk.text,
                DocumentChunk.section_title,
                DocumentChunk.page_number,
                Document.title,
                Document.id.label("document_id"),
                rank.label("rank"),
            )
            .join(
                DocumentVersion,
                DocumentVersion.id
                == DocumentChunk.document_version_id,
            )
            .join(
                Document,
                Document.id == DocumentVersion.document_id,
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.search_vector.op("@@")(ts_query),
            )
            .order_by(rank.desc())
            .limit(limit)
        )

        rows = self._db.execute(statement).all()

        return [
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "document_title": row.title,
                "text": row.text,
                "section_title": row.section_title,
                "page_number": row.page_number,
                "rank": float(row.rank),
            }
            for row in rows
        ]