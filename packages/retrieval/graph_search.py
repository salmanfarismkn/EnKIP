from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from packages.domain.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    Entity,
    EntityRelationship,
)


class GraphSearchService:
    def find_entities(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
    ) -> list[Entity]:
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

        stmt = (
            select(Entity)
            .where(Entity.tenant_id == tenant_id)
            .where(or_(*conditions))
            .limit(10)
        )

        return list(db.scalars(stmt).all())

    def related_entities(
        self,
        db: Session,
        tenant_id: UUID,
        entity_ids: list[UUID],
    ) -> list[Entity]:
        if not entity_ids:
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
            .where(Entity.tenant_id == tenant_id)
            .where(
                or_(
                    EntityRelationship.source_entity_id.in_(entity_ids),
                    EntityRelationship.target_entity_id.in_(entity_ids),
                )
            )
            .limit(30)
        )

        return list(db.scalars(stmt).unique().all())

    def relationship_chunks(
        self,
        db: Session,
        tenant_id: UUID,
        entity_ids: list[UUID],
    ) -> list[DocumentChunk]:
        if not entity_ids:
            return []

        stmt = (
            select(DocumentChunk)
            .join(
                EntityRelationship,
                EntityRelationship.source_chunk_id
                == DocumentChunk.id,
            )
            .where(DocumentChunk.tenant_id == tenant_id)
            .where(
                or_(
                    EntityRelationship.source_entity_id.in_(entity_ids),
                    EntityRelationship.target_entity_id.in_(entity_ids),
                )
            )
            .limit(30)
        )

        return list(db.scalars(stmt).unique().all())

    def search(
        self,
        db: Session,
        tenant_id: UUID,
        query: str,
        limit: int = 20,
    ) -> list[dict]:
        entities = self.find_entities(
            db=db,
            tenant_id=tenant_id,
            query=query,
        )

        if not entities:
            return []

        entity_ids = [entity.id for entity in entities]

        relationships = list(
            db.scalars(
                select(EntityRelationship)
                .where(
                    EntityRelationship.tenant_id == tenant_id
                )
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
            .where(
                DocumentChunk.tenant_id == tenant_id
            )
            .where(
                DocumentChunk.id.in_(chunk_ids)
            )
        )

        rows = db.execute(stmt).all()

        relationship_by_chunk: dict[UUID, list[str]] = {}

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
                    "graph_relationships": relationship_by_chunk.get(
                        chunk.id,
                        [],
                    ),
                    "score": 1.0,
                }
            )

        return results