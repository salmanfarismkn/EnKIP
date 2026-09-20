from uuid import UUID

from sqlalchemy.orm import Session

from packages.domain.models import Tenant 


class TenantService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_tenant(self, name: str) -> UUID:
        tenant = Tenant(name=name)

        self._db.add(tenant)
        self._db.commit()
        self._db.refresh(tenant)

        return tenant.id