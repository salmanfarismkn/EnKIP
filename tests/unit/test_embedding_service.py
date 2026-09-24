from dataclasses import dataclass


@dataclass
class FakeEmbeddingProvider:
    model_name: str = "fake-model"
    dimensions: int = 3

    def embed(self, text: str):
        raise NotImplementedError

    def embed_batch(self, texts: list[str]):
        from packages.llm.embeddings import EmbeddingResult

        return [
            EmbeddingResult(
                vector=[0.1, 0.2, 0.3],
                model=self.model_name,
            )
            for _ in texts
        ]