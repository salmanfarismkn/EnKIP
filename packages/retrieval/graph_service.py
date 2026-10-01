from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import (
    Entity,
    EntityMention,
    EntityRelationship,
)
from packages.retrieval.graph_extraction import (
    GraphExtractionResult,
)


class GraphService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def persist_extraction(
        self,
        tenant_id: UUID,
        chunk_id: UUID,
        extraction: GraphExtractionResult,
    ) -> None:
        entity_map: dict[tuple[str, str], Entity] = {}

        for extracted in extraction.entities:
            key = (
                extracted.name.strip().lower(),
                extracted.entity_type,
            )

            if not key[0]:
                continue

            entity = self._db.execute(
                select(Entity).where(
                    Entity.tenant_id == tenant_id,
                    Entity.canonical_name
                    == extracted.name.strip(),
                    Entity.entity_type
                    == extracted.entity_type,
                )
            ).scalar_one_or_none()

            if entity is None:
                entity = Entity(
                    tenant_id=tenant_id,
                    canonical_name=extracted.name.strip(),
                    entity_type=extracted.entity_type,
                )

                self._db.add(entity)
                self._db.flush()

            entity_map[key] = entity

            self._db.add(
                EntityMention(
                    tenant_id=tenant_id,
                    entity_id=entity.id,
                    chunk_id=chunk_id,
                    mention_text=extracted.mention_text,
                )
            )

        for relationship in extraction.relationships:
            source_key = (
                relationship.source_entity.strip().lower(),
                self._find_entity_type(
                    extraction,
                    relationship.source_entity,
                ),
            )

            target_key = (
                relationship.target_entity.strip().lower(),
                self._find_entity_type(
                    extraction,
                    relationship.target_entity,
                ),
            )

            source = entity_map.get(source_key)
            target = entity_map.get(target_key)

            if source is None or target is None:
                continue

            self._db.add(
                EntityRelationship(
                    tenant_id=tenant_id,
                    source_entity_id=source.id,
                    target_entity_id=target.id,
                    relationship_type=relationship.relationship_type,
                    source_chunk_id=chunk_id,
                    confidence=relationship.confidence,
                )
            )

    @staticmethod
    def _find_entity_type(
        extraction: GraphExtractionResult,
        name: str,
    ) -> str:
        normalized = name.strip().lower()

        for entity in extraction.entities:
            if entity.name.strip().lower() == normalized:
                return entity.entity_type

        raise ValueError(
            f"Relationship references unknown entity: {name}"
        )