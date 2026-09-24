from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model: str


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str:
        ...

    @property
    def dimensions(self) -> int:
        ...

    def embed(self, text: str) -> EmbeddingResult:
        ...

    def embed_batch(
        self,
        texts: list[str],
    ) -> list[EmbeddingResult]:
        ...