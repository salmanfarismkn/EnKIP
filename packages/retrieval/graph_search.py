from __future__ import annotations

from uuid import UUID


from sqlalchemy.orm import Session

from packages.domain.models import (
    Entity,
    EntityMention,
    EntityRelationship,
    DocumentChunk,
)
from sqlalchemy import or_, select
from dataclasses import dataclass



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
        if len(token.strip(".,!?():;{}[]")) >= 3
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



@dataclass(frozen=True)
class GraphCandidate:
    chunk_id: UUID
    entity_names: list[str]
    relationship_types: list[str]

def search(
    self,
    db: Session,
    tenant_id: UUID,
    query: str,
) -> list[GraphCandidate]:
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
            .limit(30)
        ).all()
    )

    candidates: list[GraphCandidate] = []

    entity_map = {
        entity.id: entity.canonical_name
        for entity in db.scalars(
            select(Entity).where(
                Entity.id.in_(
                    {
                        relationship.source_entity_id
                        for relationship in relationships
                    }
                    |
                    {
                        relationship.target_entity_id
                        for relationship in relationships
                    }
                )
            )
        ).all()
    }

    for relationship in relationships:
        candidates.append(
            GraphCandidate(
                chunk_id=relationship.source_chunk_id,
                entity_names=[
                    entity_map.get(
                        relationship.source_entity_id,
                        "",
                    ),
                    entity_map.get(
                        relationship.target_entity_id,
                        "",
                    ),
                ],
                relationship_types=[
                    relationship.relationship_type,
                ],
            )
        )

    return candidates