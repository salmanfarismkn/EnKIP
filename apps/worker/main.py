from packages.domain.database import SessionLocal
from packages.ingestion.local_storage import LocalObjectStorage
from packages.ingestion.parser_registry import ParserRegistry
from apps.api.config import settings
from packages.llm.openai_embeddings import OpenAIEmbeddingProvider

from apps.worker.services.embedding_service import EmbeddingService
from apps.worker.services.chunk_service import ChunkService
from packages.ingestion.chunker import DocumentChunker


def process_job(job_id: str) -> None:
    from uuid import UUID

    from apps.worker.services.ingestion_service import (
        IngestionService,
    )

    db = SessionLocal()

    try:
        storage = LocalObjectStorage(
            root=settings.storage_root,
        )

        embedding_provider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )

        embedding_service = EmbeddingService(
            db=db,
            provider=embedding_provider,
        )

        parser_registry = ParserRegistry()

        chunker = DocumentChunker()

        chunk_service = ChunkService(
            db=db,
        )

        service = IngestionService(
            db=db,
            storage=storage,
            parser_registry=parser_registry,
            chunker=chunker,
            chunk_service=chunk_service,
            embedding_service=embedding_service,
        )

        service.process_job(UUID(job_id))

    finally:
        db.close()


def main() -> None:
    print("Enterprise Knowledge Platform Worker")


if __name__ == "__main__":
    main()