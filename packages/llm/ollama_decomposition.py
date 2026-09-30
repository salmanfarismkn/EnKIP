import json

import requests

from packages.retrieval.query_decomposition import (
    DecomposedQuery,
    SubQuery,
)
from packages.llm.prompts import (
    DECOMPOSITION_SYSTEM_PROMPT,
)


class OllamaQueryDecomposer:
    def __init__(
        self,
        model_name: str,
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url

    def decompose(
        self,
        query: str,
    ) -> DecomposedQuery:
        if not query.strip():
            raise ValueError("Query must not be empty")

        response = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model_name,
                "stream": False,
                "format": "json",
                "messages": [
                    {
                        "role": "system",
                        "content": DECOMPOSITION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": query,
                    },
                ],
            },
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        content = data["message"]["content"]

        parsed = json.loads(content)

        raw_queries = parsed.get("queries", [])

        if not isinstance(raw_queries, list):
            raise ValueError(
                "Decomposer returned invalid query list"
            )

        sub_queries: list[SubQuery] = []

        seen: set[str] = set()

        for item in raw_queries[:5]:
            if isinstance(item, str):
                sub_query = item.strip()
                purpose = "general"
            elif isinstance(item, dict):
                sub_query = str(
                    item.get("query", "")
                ).strip()

                purpose = str(
                    item.get("purpose", "")
                ).strip()
            else:
                continue

            if not sub_query:
                continue

            if not purpose:
                purpose = "general"

            normalized = sub_query.lower()

            if normalized in seen:
                continue

            seen.add(normalized)
            
            sub_queries.append(
                SubQuery(
                    query=sub_query,
                    purpose=purpose,
                )
            )

        if not sub_queries:
            sub_queries.append(
                SubQuery(
                    query=query,
                    purpose="original query",
                )
            )

        return DecomposedQuery(
            original_query=query,
            sub_queries=sub_queries,
        )