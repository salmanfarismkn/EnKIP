from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.domain.models import (
    DataSource,
    Document,
    DocumentChunk,
    DocumentVersion,
)
from packages.permissions.service import PermissionService


class LexicalSearchService:
    def __init__(
        self,
        db: Session,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._db = db
        self._permission_service = (
            permission_service
            or PermissionService()
        )

    def search(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
        user_id: UUID | None = None,
        limit: int = 10,
    ) -> list:
        if not query.strip():
            raise ValueError("Query must not be empty")

        if limit <= 0:
            raise ValueError("Limit must be positive")

        accessible_sources = (
            self._permission_service
            .get_accessible_data_source_ids(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        )

        if not accessible_sources:
            return []

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
                Document.id
                == DocumentVersion.document_id,
            )
            .join(
                DataSource,
                DataSource.id
                == Document.data_source_id,
            )
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.search_vector.op("@@")(ts_query),
                DataSource.id.in_(accessible_sources),
            )
            .order_by(rank.desc())
            .limit(limit)
        )

        rows = db.execute(statement).all()

        return [
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "document_title": row.title,
                "text": row.text,
                "section_title": row.section_title,
                "page_number": row.page_number,
                "rank": float(row.rank),
                "retrieval_score": float(row.rank),
            }
            for row in rows
        ]