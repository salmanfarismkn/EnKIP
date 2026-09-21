from uuid import UUID

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: UUID
    version_id: UUID
    ingestion_job_id: UUID