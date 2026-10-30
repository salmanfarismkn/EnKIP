from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth import AuthenticatedPrincipal, get_authenticated_principal
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
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    db: Session = Depends(get_db),
) -> Tenant:
    del principal
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tenant creation is a system-level operation and is not available through this API",
    )

    # This code is unreachable until a deliberate system bootstrap path is implemented.
    service = TenantService(db)
    tenant_id = service.create_tenant(payload.name)

    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise RuntimeError("Tenant was created but could not be loaded")

    return tenant