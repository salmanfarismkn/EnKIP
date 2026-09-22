import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import (
    Document,
    DocumentVersion,
    IngestionJob,
)
from packages.ingestion.storage import ObjectStorage


class DocumentService:
    def __init__(
        self,
        db: Session,
        storage: ObjectStorage,
    ) -> None:
        self._db = db
        self._storage = storage

    def create_document(
        self,
        tenant_id: UUID,
        data_source_id: UUID,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> tuple[Document, DocumentVersion, IngestionJob]:

        if not content:
            raise ValueError("Document content cannot be empty")

        checksum = hashlib.sha256(content).hexdigest()

        existing_document = self._find_existing_document(
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            checksum=checksum,
        )

        if existing_document is not None:
            raise ValueError(
                "An identical document version already exists"
            )

        document = Document(
            tenant_id=tenant_id,
            data_source_id=data_source_id,
            title=filename,
            mime_type=mime_type,
            object_key="pending",
        )

        self._db.add(document)
        self._db.flush()

        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            checksum=checksum,
        )

        self._db.add(version)
        self._db.flush()

        object_key = (
            f"tenant/{tenant_id}/"
            f"documents/{document.id}/"
            f"versions/{version.id}/"
            f"source"
        )

        print(
            f"Storing {filename}: "
            f"{len(content)} bytes"
        )
        
        self._storage.put(
            object_key,
            content,
        )

        stored_content = self._storage.get(object_key)

        if len(stored_content) != len(content):
            raise RuntimeError(
                "Stored object size does not match uploaded content"
            )
        
        document.object_key = object_key

        job = IngestionJob(
            tenant_id=tenant_id,
            document_version_id=version.id,
        )

        self._db.add(job)

        self._db.commit()

        self._db.refresh(document)
        self._db.refresh(version)
        self._db.refresh(job)

        return document, version, job

    def _find_existing_document(
        self,
        tenant_id: UUID,
        data_source_id: UUID,
        checksum: str,
    ) -> DocumentVersion | None:

        statement = (
            select(DocumentVersion)
            .join(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.data_source_id == data_source_id,
                DocumentVersion.checksum == checksum,
            )
        )

        return self._db.execute(statement).scalar_one_or_none()