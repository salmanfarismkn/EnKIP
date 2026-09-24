import hashlib

from packages.llm.embeddings import EmbeddingResult


class FakeEmbeddingProvider:
    def __init__(
        self,
        dimensions: int,
        model_name: str = "fake-embedding",
        model_version: str = "1",
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")

        self._dimensions = dimensions
        self._model_name = model_name
        self._model_version = model_version

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> EmbeddingResult:
        return self.embed_batch([text])[0]

    def embed_batch(
        self,
        texts: list[str],
    ) -> list[EmbeddingResult]:
        results: list[EmbeddingResult] = []

        for text in texts:
            vector: list[float] = []

            for index in range(self._dimensions):
                digest = hashlib.sha256(
                    f"{index}:{text}".encode("utf-8")
                ).digest()

                value = int.from_bytes(
                    digest[:4],
                    byteorder="big",
                )

                normalized = (value / 2**32) * 2 - 1
                vector.append(normalized)

            results.append(
                EmbeddingResult(
                    vector=vector,
                    model=self._model_name,
                    version=self._model_version,
                )
            )

        return results