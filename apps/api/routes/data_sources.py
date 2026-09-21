from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.data_source import (
    DataSourceCreate,
    DataSourceResponse,
)
from apps.api.services.data_source_service import DataSourceService

router = APIRouter(
    prefix="/tenants/{tenant_id}/data-sources",
    tags=["data-sources"],
)


@router.post(
    "",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_data_source(
    tenant_id: UUID,
    payload: DataSourceCreate,
    db: Session = Depends(get_db),
) -> DataSourceResponse:
    service = DataSourceService(db)

    return service.create(
        tenant_id=tenant_id,
        name=payload.name,
        source_type=payload.source_type,
    )