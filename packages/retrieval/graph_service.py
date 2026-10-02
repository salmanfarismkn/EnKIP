from sqlalchemy.dialects.postgresql import insert
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
    def persist_extraction(
        self,
        db: Session,
        tenant_id,
        chunk_id,
        extraction: GraphExtractionResult,
    ) -> None:
        entity_map: dict[tuple[str, str], Entity] = {}

        for extracted in extraction.entities:
            canonical_name = extracted.name.strip()
            entity_type = extracted.entity_type.strip()

            stmt = (
                insert(Entity)
                .values(
                    tenant_id=tenant_id,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                )
                .on_conflict_do_nothing(
                    constraint="uq_entity_tenant_name_type"
                )
            )

            db.execute(stmt)

            entity = (
                db.query(Entity)
                .filter(
                    Entity.tenant_id == tenant_id,
                    Entity.canonical_name == canonical_name,
                    Entity.entity_type == entity_type,
                )
                .one()
            )

            entity_map[
                (canonical_name.lower(), entity_type)
            ] = entity

            mention_stmt = (
                insert(EntityMention)
                .values(
                    tenant_id=tenant_id,
                    entity_id=entity.id,
                    chunk_id=chunk_id,
                    mention_text=extracted.mention_text,
                )
                .on_conflict_do_nothing(
                    constraint="uq_entity_mention"
                )
            )

            db.execute(mention_stmt)

        for relationship in extraction.relationships:
            source = self._find_entity(
                entity_map,
                relationship.source_entity,
            )

            target = self._find_entity(
                entity_map,
                relationship.target_entity,
            )

            if source is None or target is None:
                continue

            relationship_stmt = (
                insert(EntityRelationship)
                .values(
                    tenant_id=tenant_id,
                    source_entity_id=source.id,
                    target_entity_id=target.id,
                    relationship_type=relationship.relationship_type,
                    source_chunk_id=chunk_id,
                    confidence=relationship.confidence,
                )
                .on_conflict_do_nothing(
                    constraint="uq_entity_relationship"
                )
            )

            db.execute(relationship_stmt)

    @staticmethod
    def _find_entity(
        entity_map: dict[tuple[str, str], Entity],
        name: str,
    ) -> Entity | None:
        matches = [
            entity
            for (canonical_name, _), entity in entity_map.items()
            if canonical_name == name.lower()
        ]

        if not matches:
            return None

        return matches[0]