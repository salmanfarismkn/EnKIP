from dataclasses import dataclass

from packages.retrieval.graph_types import (
    EntityType,
    RelationshipType,
)


@dataclass(frozen=True)
class ExtractedEntity:
    name: str
    entity_type: str
    mention_text: str


@dataclass(frozen=True)
class ExtractedRelationship:
    source_entity: str
    target_entity: str
    relationship_type: str
    confidence: float


@dataclass(frozen=True)
class GraphExtractionResult:
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]


def validate_extraction(
    extraction: GraphExtractionResult,
) -> GraphExtractionResult:
    valid_entity_types = {item.value for item in EntityType}
    valid_relationship_types = {item.value for item in RelationshipType}

    entities: list[ExtractedEntity] = []

    for entity in extraction.entities:
        if entity.entity_type not in valid_entity_types:
            continue

        if not entity.name.strip():
            continue

        if not entity.mention_text.strip():
            continue

        entities.append(entity)

    entity_names = {entity.name.lower() for entity in entities}

    relationships: list[ExtractedRelationship] = []

    for relationship in extraction.relationships:
        if relationship.relationship_type not in valid_relationship_types:
            continue

        if relationship.source_entity.lower() not in entity_names:
            continue

        if relationship.target_entity.lower() not in entity_names:
            continue

        confidence = max(
            0.0,
            min(1.0, relationship.confidence),
        )

        relationships.append(
            ExtractedRelationship(
                source_entity=relationship.source_entity,
                target_entity=relationship.target_entity,
                relationship_type=relationship.relationship_type,
                confidence=confidence,
            )
        )

    return GraphExtractionResult(
        entities=entities,
        relationships=relationships,
    )