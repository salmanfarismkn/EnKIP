from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.document import DocumentUploadResponse
from apps.api.services.document_service import DocumentService
from packages.ingestion.local_storage import LocalObjectStorage
from apps.api.config import settings

router = APIRouter(
    prefix="/tenants/{tenant_id}/documents",
    tags=["documents"],
)


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    tenant_id: UUID,
    data_source_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    storage = LocalObjectStorage(
        root=settings.storage_root,
    )

    service = DocumentService(
        db=db,
        storage=storage,
    )

    document, version, job = service.create_document(
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        filename=file.filename or "unnamed",
        mime_type=file.content_type or "application/octet-stream",
        content=content,
    )

    return DocumentUploadResponse(
        id=document.id,
        version_id=version.id,
        ingestion_job_id=job.id,
    )
