from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import DataSource, DataSourceAccess


class PermissionService:
    def get_accessible_data_source_ids(
        self,
        db: Session,
        tenant_id: UUID,
        user_id: UUID | None,
    ) -> set[UUID]:
        if user_id is None:
            access_configured = db.scalar(
                select(DataSourceAccess.id)
                .where(
                    DataSourceAccess.tenant_id == tenant_id
                )
                .limit(1)
            )

            if access_configured is not None:
                return set()

            return set(
                db.scalars(
                    select(DataSource.id)
                    .where(DataSource.tenant_id == tenant_id)
                ).all()
            )

        stmt = (
            select(DataSourceAccess.data_source_id)
            .where(
                DataSourceAccess.tenant_id == tenant_id
            )
            .where(
                DataSourceAccess.user_id == user_id
            )
        )

        return set(db.scalars(stmt).all())

    def can_access_data_source(
        self,
        db: Session,
        tenant_id: UUID,
        user_id: UUID | None,
        data_source_id: UUID,
    ) -> bool:
        if user_id is None:
            return data_source_id in self.get_accessible_data_source_ids(
                db=db,
                tenant_id=tenant_id,
                user_id=None,
            )

        stmt = (
            select(DataSourceAccess.id)
            .where(
                DataSourceAccess.tenant_id == tenant_id
            )
            .where(
                DataSourceAccess.user_id == user_id
            )
            .where(
                DataSourceAccess.data_source_id
                == data_source_id
            )
            .limit(1)
        )

        return db.scalar(stmt) is not None