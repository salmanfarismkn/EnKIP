import requests

from packages.llm.context import build_context
from packages.llm.generation import GeneratedAnswer
from packages.llm.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from packages.retrieval import evidence
from packages.retrieval.evidence import Evidence


class OllamaAnswerGenerator:
    def __init__(
        self,
        model_name: str,
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url

    def generate(
        self,
        query: str,
        evidence: list[Evidence],
    ) -> GeneratedAnswer:
        if not query.strip():
            raise ValueError("Query must not be empty")

        if not evidence:
            return GeneratedAnswer(
                answer=(
                    "I could not find enough relevant information "
                    "in the knowledge base to answer this question."
                ),
                evidence=[],
            )

        context = build_context(evidence)

        response = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model_name,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            query=query,
                            context=context,
                        ),
                    },
                ],
            },
            timeout=180,
        )

        response.raise_for_status()

        data = response.json()

        answer = data["message"]["content"].strip()

        return GeneratedAnswer(
            answer=answer,
            evidence=evidence,
            grounded=bool(evidence),
        )