from packages.domain.database import SessionLocal
from packages.ingestion.local_storage import LocalObjectStorage
from packages.ingestion.parser_registry import ParserRegistry
from apps.api.config import settings
from packages.llm.ollama_embeddings import OllamaEmbeddingProvider

from apps.worker.services.embedding_service import EmbeddingService
from apps.worker.services.chunk_service import ChunkService
from packages.ingestion.chunker import DocumentChunker


import time
from uuid import UUID

from apps.api.config import settings
from apps.worker.services.chunk_service import ChunkService
from apps.worker.services.embedding_service import (
    EmbeddingService,
)
from apps.worker.services.job_queue import JobQueue
from apps.worker.services.ingestion_service import (
    IngestionService,
)
from packages.domain.database import SessionLocal
from packages.ingestion.chunker import DocumentChunker
from packages.ingestion.local_storage import (
    LocalObjectStorage,
)
from packages.ingestion.parser_registry import (
    ParserRegistry,
)
from packages.llm.ollama_embeddings import (
    OllamaEmbeddingProvider,
)


queue = JobQueue()


def process_job(job_id: str) -> None:
    db = SessionLocal()

    try:
        storage = LocalObjectStorage(
            root=settings.storage_root,
        )

        embedding_provider = OllamaEmbeddingProvider(
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            base_url=settings.ollama_base_url,
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


def run_worker() -> None:
    while True:
        db = SessionLocal()

        try:
            queue.recover_stale_jobs(db)

            job_id = queue.claim_next(db)

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

        if job_id is None:
            time.sleep(2)
            continue

        try:
            process_job(str(job_id))

        except Exception as exc:
            print(
                f"Failed processing job "
                f"{job_id}: {exc}"
            )


def main() -> None:
    run_worker()


if __name__ == "__main__":
    main()