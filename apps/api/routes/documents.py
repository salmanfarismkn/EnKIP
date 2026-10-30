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

from apps.api.auth import AuthenticatedPrincipal, get_authenticated_principal, require_tenant_admin
from apps.api.dependencies import get_db
from apps.api.schemas.document import DocumentUploadResponse
from apps.api.services.document_service import DocumentService
from packages.ingestion.local_storage import LocalObjectStorage
from packages.ingestion.upload_validation import (
    UploadValidationError,
    validate_upload_content,
)
from apps.api.config import settings
from packages.domain.models import DataSource

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
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    require_tenant_admin(tenant_id, principal, db)
    data_source = db.get(DataSource, data_source_id)
    if data_source is None or data_source.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found in this tenant",
        )
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail="Uploaded file exceeds the configured size limit",
        )

    chunks: list[bytes] = []
    received_bytes = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        received_bytes += len(chunk)
        if received_bytes > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail="Uploaded file exceeds the configured size limit",
            )
        chunks.append(chunk)

    content = b"".join(chunks)

    try:
        validate_upload_content(
            content,
            file.content_type or "application/octet-stream",
            max_pdf_pages=settings.max_pdf_pages,
        )
    except UploadValidationError as exc:
        if file.content_type not in {
            "text/plain",
            "text/markdown",
            "application/pdf",
        }:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

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
