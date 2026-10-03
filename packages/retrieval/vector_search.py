from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
)
from packages.llm.embeddings import EmbeddingProvider
from packages.domain.models import DataSource
from packages.permissions.service import PermissionService

class VectorSearchService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._db = db
        self._embedding_provider = embedding_provider
        self._permission_service = permission_service or PermissionService()

    def search(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
        user_id: UUID | None = None,
        limit: int = 10,
    ) -> list[dict]:
        if not query or not query.strip():
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

        query_embedding = self._embedding_provider.embed(
            query
        )

        distance = (
            ChunkEmbedding.embedding.cosine_distance(
                query_embedding.vector
            )
        )

        statement = (
            select(
                DocumentChunk.id,
                DocumentChunk.text,
                DocumentChunk.section_title,
                DocumentChunk.page_number,
                Document.title,
                Document.id.label("document_id"),
                distance.label("distance"),
            )
            .join(
                ChunkEmbedding,
                ChunkEmbedding.chunk_id == DocumentChunk.id,
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
            .join(
                DataSource,
                DataSource.id == Document.data_source_id,
            )
            .where(
                ChunkEmbedding.tenant_id == tenant_id,
                DocumentChunk.tenant_id == tenant_id,
                ChunkEmbedding.model_name
                == self._embedding_provider.model_name,
                ChunkEmbedding.model_version
                == self._embedding_provider.model_version,
                ChunkEmbedding.dimensions
                == self._embedding_provider.dimensions,
                DataSource.id.in_(accessible_sources),
            )
            .order_by(distance)
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
                "distance": float(row.distance),
                "score": 1.0 - float(row.distance),
            }
            for row in rows
        ]