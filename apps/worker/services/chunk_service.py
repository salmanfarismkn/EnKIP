from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from packages.domain.models import DocumentChunk
from packages.ingestion.chunker import Chunk


class ChunkService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def replace_chunks(
        self,
        tenant_id: UUID,
        document_version_id: UUID,
        chunks: list[Chunk],
    ) -> None:

        self._db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_version_id
                == document_version_id
            )
        )

        for chunk in chunks:
            self._db.add(
                DocumentChunk(
                    tenant_id=tenant_id,
                    document_version_id=document_version_id,
                    chunk_index=chunk.chunk_index,
                    section_title=chunk.section_title,
                    text=chunk.text,
                    page_number=chunk.page_number,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                )
            )