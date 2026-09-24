from datetime import datetime, timezone
from marshal import version
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import (
    Document,
    DocumentProcessingStatus,
    DocumentVersion,
    IngestionJob,
    IngestionStatus,
)
from packages.ingestion.parser_registry import ParserRegistry
from packages.ingestion.storage import ObjectStorage
from packages.ingestion.chunker import DocumentChunker
from apps.worker.services.chunk_service import ChunkService

class IngestionService:
    def __init__(
        self,
        db: Session,
        storage: ObjectStorage,
        parser_registry: ParserRegistry,
    ) -> None:
        self._db = db
        self._storage = storage
        self._parser_registry = parser_registry
        self._chunker = DocumentChunker()
        self._chunk_service = ChunkService(db)

    def process_job(self, job_id: UUID) -> None:
        job = self._get_job(job_id)

        if job.status == IngestionStatus.COMPLETED:
            return

        job.status = IngestionStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)

        self._db.commit()

        try:
            version = self._get_version(
                job.document_version_id
            )

            document = self._get_document(
                version.document_id
            )

            version.processing_status = (
                DocumentProcessingStatus.PROCESSING
            )

            self._db.commit()

            content = self._storage.get(
                document.object_key
            )

            parser = self._parser_registry.get_parser(
                document.mime_type
            )

            parsed = parser.parse(
                content=content,
                filename=document.title,
            )

            chunks = self._chunker.chunk(parsed)

            self._chunk_service.replace_chunks(
                tenant_id=job.tenant_id,
                document_version_id=version.id,
                chunks=chunks,
            )

            version.extracted_text = parsed.text

            version.processing_status = (
                DocumentProcessingStatus.COMPLETED
            )

            job.status = IngestionStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = None

            self._db.commit()

        except Exception as exc:
            self._handle_failure(job, exc)

            raise

    def _get_job(self, job_id: UUID) -> IngestionJob:
        statement = select(IngestionJob).where(
            IngestionJob.id == job_id
        )

        job = self._db.execute(statement).scalar_one_or_none()

        if job is None:
            raise ValueError(
                f"Ingestion job not found: {job_id}"
            )

        return job

    def _get_version(
        self,
        version_id: UUID,
    ) -> DocumentVersion:

        version = self._db.get(
            DocumentVersion,
            version_id,
        )

        if version is None:
            raise ValueError(
                f"Document version not found: {version_id}"
            )

        return version

    def _get_document(
        self,
        document_id: UUID,
    ) -> Document:

        document = self._db.get(
            Document,
            document_id,
        )

        if document is None:
            raise ValueError(
                f"Document not found: {document_id}"
            )

        return document

    def _handle_failure(
        self,
        job: IngestionJob,
        error: Exception,
    ) -> None:

        job.status = IngestionStatus.FAILED
        job.error_message = str(error)
        job.completed_at = datetime.now(timezone.utc)

        version = self._get_version(
            job.document_version_id
        )

        version.processing_status = (
            DocumentProcessingStatus.FAILED
        )
        version.processing_error = str(error)

        self._db.commit()