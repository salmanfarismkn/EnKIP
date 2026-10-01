from dataclasses import dataclass


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