import logging
import signal
import threading
import time
from uuid import UUID

from apps.api.config import settings
from apps.worker.services.chunk_service import ChunkService
from apps.worker.services.embedding_service import EmbeddingService
from apps.worker.services.ingestion_service import IngestionService
from apps.worker.services.job_queue import JobQueue
from apps.api.config import validate_deployment_configuration
from packages.domain.database import SessionLocal
from packages.ingestion.chunker import DocumentChunker
from packages.ingestion.local_storage import LocalObjectStorage
from packages.ingestion.parser_registry import ParserRegistry
from packages.llm.ollama_embeddings import OllamaEmbeddingProvider


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


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

        parser_registry = ParserRegistry(
            max_pdf_pages=settings.max_pdf_pages,
        )

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


def run_worker(
    stop_event: threading.Event | None = None,
    poll_interval_seconds: float = 2.0,
) -> None:
    stop_event = stop_event or threading.Event()

    while not stop_event.is_set():
        db = SessionLocal()

        try:
            queue.recover_stale_jobs(db)
            job_id = queue.claim_next(db)
        except Exception:
            db.rollback()
            logger.warning(
                "Worker database polling failed",
                extra={
                    "event": "worker_database_poll_failed",
                    "action": "retry_bounded",
                    "retry_interval_seconds": poll_interval_seconds,
                },
            )
            job_id = None

        finally:
            db.close()

        if job_id is None:
            stop_event.wait(poll_interval_seconds)
            continue

        try:
            process_job(str(job_id))
        except Exception as exc:
            logger.error(
                "Ingestion job %s processing failed: category=%s action=%s",
                job_id,
                getattr(
                    exc,
                    "failure_category",
                    "processing_error",
                ),
                "retry_or_terminal",
                extra={
                    "event": "ingestion_job_failed",
                    "job_id": str(job_id),
                    "failure_category": getattr(
                        exc,
                        "failure_category",
                        "processing_error",
                    ),
                    "action": "retry_or_terminal",
                },
                exc_info=False,
            )


def main() -> None:
    validate_deployment_configuration()
    stop_event = threading.Event()

    def request_shutdown(signum: int, frame: object) -> None:
        del frame
        logger.info(
            "Worker shutdown requested",
            extra={
                "event": "worker_shutdown_requested",
                "signal": signum,
                "action": "finish_claimed_job_and_stop",
            },
        )
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    run_worker(stop_event=stop_event)


if __name__ == "__main__":
    main()