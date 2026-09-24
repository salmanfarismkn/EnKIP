from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import ChunkEmbedding, DocumentChunk
from packages.llm.embeddings import EmbeddingProvider


class EmbeddingService:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider,
    ) -> None:
        self._db = db
        self._provider = provider

    def embed_chunks(
        self,
        tenant_id: UUID,
        chunks: list[DocumentChunk],
    ) -> None:
        if not chunks:
            return

        results = self._provider.embed_batch(
            [chunk.text for chunk in chunks]
        )

        if len(results) != len(chunks):
            raise RuntimeError(
                "Embedding provider returned an unexpected "
                "number of vectors"
            )

        for chunk, result in zip(chunks, results, strict=True):
            if len(result.vector) != self._provider.dimensions:
                raise ValueError(
                    f"Embedding dimension mismatch: "
                    f"expected {self._provider.dimensions}, "
                    f"got {len(result.vector)}"
                )

            existing = self._db.execute(
                select(ChunkEmbedding).where(
                    ChunkEmbedding.chunk_id == chunk.id,
                    ChunkEmbedding.model_name == result.model,
                    ChunkEmbedding.model_version == result.version,
                )
            ).scalar_one_or_none()

            if existing is not None:
                continue

            self._db.add(
                ChunkEmbedding(
                    tenant_id=tenant_id,
                    chunk_id=chunk.id,
                    model_name=result.model,
                    model_version=result.version,
                    dimensions=len(result.vector),
                    embedding=result.vector,
                )
            )