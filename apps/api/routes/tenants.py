from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from apps.api.dependencies import get_db
from apps.api.schemas.tenant import TenantCreate, TenantResponse
from apps.api.services.tenant_service import TenantService
from packages.domain.models import Tenant

router = APIRouter(
    prefix="/tenants",
    tags=["tenants"],
)


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant(
    payload: TenantCreate,
    db: Session = Depends(get_db),
) -> Tenant:
    service = TenantService(db)

    tenant_id = service.create_tenant(payload.name)

    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise RuntimeError("Tenant was created but could not be loaded")

    return tenant