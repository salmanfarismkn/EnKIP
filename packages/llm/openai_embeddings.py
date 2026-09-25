from openai import OpenAI

from packages.llm.embeddings import EmbeddingResult


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        dimensions: int,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")

        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")

        self._client = OpenAI(api_key=api_key)
        self._model_name = model_name
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return "1"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> EmbeddingResult:
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(
        self,
        texts: list[str],
    ) -> list[EmbeddingResult]:
        if not texts:
            return []

        response = self._client.embeddings.create(
            model=self._model_name,
            input=texts,
            dimensions=self._dimensions,
        )

        ordered = sorted(
            response.data,
            key=lambda item: item.index,
        )

        return [
            EmbeddingResult(
                vector=item.embedding,
                model=response.model,
                version=self.model_version,
            )
            for item in ordered
        ]