from typing import Protocol


class Reranker(Protocol):
    @property
    def model_name(self) -> str:
        ...

    def rerank(
        self,
        query: str,
        results: list[dict],
    ) -> list[dict]:
        ...