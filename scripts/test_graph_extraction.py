from apps.api.config import settings
from packages.llm.ollama_graph_extraction import OllamaGraphExtractor
from packages.retrieval.graph_extraction import validate_extraction


text = """
Incident INC-47291 affected the Payment Service.
The Payments Team owns the Payment Service.
The incident was fixed by the Payments Team.
The Payment Service uses Redis for caching.
"""


extractor = OllamaGraphExtractor(
    base_url=settings.ollama_base_url,
    model=settings.generation_model,
)

result = extractor.extract(text)
result = validate_extraction(result)

print("\nENTITIES")

for entity in result.entities:
    print(
        f"- {entity.name} "
        f"[{entity.entity_type}] "
        f"mention={entity.mention_text}"
    )

print("\nRELATIONSHIPS")

for relationship in result.relationships:
    print(
        f"- {relationship.source_entity}"
        f" --{relationship.relationship_type}--> "
        f"{relationship.target_entity}"
        f" ({relationship.confidence:.2f})"
    )