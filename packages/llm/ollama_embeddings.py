from dataclasses import dataclass

import requests

from packages.llm.embeddings import EmbeddingResult


@dataclass
class OllamaEmbeddingProvider:
    model_name: str
    dimensions: int
    base_url: str = "http://localhost:11434"

    @property
    def model_version(self) -> str:
        return "1"

    def embed(self, text: str) -> EmbeddingResult:
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(
        self,
        texts: list[str],
    ) -> list[EmbeddingResult]:
        if not texts:
            return []

        response = requests.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.model_name,
                "input": texts,
                "dimensions": self.dimensions,
            },
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        embeddings = data["embeddings"]

        if len(embeddings) != len(texts):
            raise RuntimeError(
                "Ollama returned an unexpected number "
                "of embeddings"
            )

        results = []

        for vector in embeddings:
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"Embedding dimension mismatch: "
                    f"expected {self.dimensions}, "
                    f"got {len(vector)}"
                )

            results.append(
                EmbeddingResult(
                    vector=vector,
                    model=self.model_name,
                    version=self.model_version,
                )
            )

        return results