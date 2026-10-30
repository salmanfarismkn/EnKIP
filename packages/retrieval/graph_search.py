from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from packages.domain.models import (
    DataSource,
    Document,
    DocumentChunk,
    DocumentVersion,
    Entity,
    EntityRelationship,
)
from packages.permissions.service import PermissionService


class GraphSearchService:
    def __init__(
        self,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._permission_service = (
            permission_service
            or PermissionService()
        )

    def find_entities(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
        user_id: UUID | None = None,
    ) -> list:
        if not query.strip():
            raise ValueError("Query must not be empty")

        tokens = {
            token.strip(".,!?():;[]{}").lower()
            for token in query.split()
            if len(token.strip(".,!?():;[]{}")) >= 3
        }

        if not tokens:
            return []

        conditions = [
            Entity.canonical_name.ilike(f"%{token}%")
            for token in tokens
        ]

        accessible_sources = self._permission_service.get_accessible_data_source_ids(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if not accessible_sources:
            return []

        stmt = (
            select(Entity)
            .join(
                EntityRelationship,
                or_(
                    EntityRelationship.source_entity_id == Entity.id,
                    EntityRelationship.target_entity_id == Entity.id,
                ),
            )
            .join(DocumentChunk, DocumentChunk.id == EntityRelationship.source_chunk_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(DataSource, DataSource.id == Document.data_source_id)
            .where(Entity.tenant_id == tenant_id)
            .where(DocumentChunk.tenant_id == tenant_id)
            .where(DataSource.id.in_(accessible_sources))
            .where(or_(*conditions))
            .distinct()
            .limit(10)
        )

        return list(db.scalars(stmt).all())

    def related_entities(
        self,
        db: Session,
        tenant_id: UUID,
        entity_ids: list[UUID],
        user_id: UUID | None = None,
    ) -> list:
        if not entity_ids:
            return []

        accessible_sources = self._permission_service.get_accessible_data_source_ids(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if not accessible_sources:
            return []

        stmt = (
            select(Entity)
            .join(
                EntityRelationship,
                or_(
                    EntityRelationship.source_entity_id == Entity.id,
                    EntityRelationship.target_entity_id == Entity.id,
                ),
            )
            .join(DocumentChunk, DocumentChunk.id == EntityRelationship.source_chunk_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(DataSource, DataSource.id == Document.data_source_id)
            .where(Entity.tenant_id == tenant_id)
            .where(DocumentChunk.tenant_id == tenant_id)
            .where(DataSource.id.in_(accessible_sources))
            .where(
                or_(
                    EntityRelationship.source_entity_id.in_(entity_ids),
                    EntityRelationship.target_entity_id.in_(entity_ids),
                )
            )
            .limit(30)
        )

        return list(
            db.scalars(stmt).unique().all()
        )

    def relationship_chunks(
        self,
        db: Session,
        tenant_id: UUID,
        entity_ids: list[UUID],
        user_id: UUID | None = None,
    ) -> list:
        if not entity_ids:
            return []

        accessible_sources = self._permission_service.get_accessible_data_source_ids(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if not accessible_sources:
            return []

        stmt = (
            select(DocumentChunk)
            .join(
                EntityRelationship,
                EntityRelationship.source_chunk_id
                == DocumentChunk.id,
            )
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(DataSource, DataSource.id == Document.data_source_id)
            .where(
                DocumentChunk.tenant_id
                == tenant_id
            )
            .where(DataSource.id.in_(accessible_sources))
            .where(
                or_(
                    EntityRelationship.source_entity_id.in_(
                        entity_ids
                    ),
                    EntityRelationship.target_entity_id.in_(
                        entity_ids
                    ),
                )
            )
            .limit(30)
        )

        return list(
            db.scalars(stmt).unique().all()
        )

    def search(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
        user_id: UUID | None = None,
        limit: int = 20,
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

        entities = self.find_entities(
            db=db,
            tenant_id=tenant_id,
            query=query,
            user_id=user_id,
        )

        if not entities:
            return []

        entity_ids = [
            entity.id
            for entity in entities
        ]

        relationships = list(
            db.scalars(
                select(EntityRelationship)
                .join(DocumentChunk, DocumentChunk.id == EntityRelationship.source_chunk_id)
                .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .join(DataSource, DataSource.id == Document.data_source_id)
                .where(EntityRelationship.tenant_id == tenant_id)
                .where(DocumentChunk.tenant_id == tenant_id)
                .where(DataSource.id.in_(accessible_sources))
                .where(
                    or_(
                        EntityRelationship.source_entity_id.in_(entity_ids),
                        EntityRelationship.target_entity_id.in_(entity_ids),
                    )
                )
                .limit(limit)
            ).all()
        )

        if not relationships:
            return []

        chunk_ids = {
            relationship.source_chunk_id
            for relationship in relationships
        }

        stmt = (
            select(
                DocumentChunk,
                DocumentVersion,
                Document,
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
                DocumentChunk.tenant_id
                == tenant_id
            )
            .where(
                DocumentChunk.id.in_(chunk_ids)
            )
            .where(
                DataSource.id.in_(
                    accessible_sources
                )
            )
        )

        rows = db.execute(stmt).all()

        relationship_by_chunk: dict[
            UUID,
            list[str],
        ] = {}

        for relationship in relationships:
            relationship_by_chunk.setdefault(
                relationship.source_chunk_id,
                [],
            ).append(
                relationship.relationship_type
            )

        results: list[dict] = []

        for chunk, version, document in rows:
            results.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "document_title": document.title,
                    "text": chunk.text,
                    "section_title": chunk.section_title,
                    "page_number": chunk.page_number,
                    "graph_relationships": (
                        relationship_by_chunk.get(
                            chunk.id,
                            [],
                        )
                    ),
                }
            )

        return results