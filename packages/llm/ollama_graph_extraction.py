from __future__ import annotations

import requests

from packages.llm.prompts import GRAPH_EXTRACTION_SYSTEM_PROMPT
from packages.retrieval.graph_extraction import (
    ExtractedEntity,
    ExtractedRelationship,
    GraphExtractionResult,
)


class OllamaGraphExtractor:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: int = 120,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model
        self._timeout = timeout

    def extract(self, text: str) -> GraphExtractionResult:
        response = requests.post(
            self._url,
            json={
                "model": self._model,
                "stream": False,
                "format": "json",
                "messages": [
                    {
                        "role": "system",
                        "content": GRAPH_EXTRACTION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
            },
            timeout=self._timeout,
        )

        response.raise_for_status()

        payload = response.json()

        content = payload["message"]["content"]

        import json

        data = json.loads(content)

        entities = [
            ExtractedEntity(
                name=item["name"].strip(),
                entity_type=item["entity_type"].strip(),
                mention_text=item["mention_text"].strip(),
            )
            for item in data.get("entities", [])
            if item.get("name")
            and item.get("entity_type")
            and item.get("mention_text")
        ]

        relationships = [
            ExtractedRelationship(
                source_entity=item["source_entity"].strip(),
                target_entity=item["target_entity"].strip(),
                relationship_type=item["relationship_type"].strip(),
                confidence=float(item["confidence"]),
            )
            for item in data.get("relationships", [])
            if item.get("source_entity")
            and item.get("target_entity")
            and item.get("relationship_type")
        ]

        return GraphExtractionResult(
            entities=entities,
            relationships=relationships,
        )