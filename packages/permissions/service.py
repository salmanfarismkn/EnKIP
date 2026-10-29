from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import (
    DataSource,
    DataSourceAccess,
    Document,
    DocumentChunk,
    DocumentVersion,
    User,
)


class PermissionService:
    def get_accessible_data_source_ids(
        self,
        db: Session,
        tenant_id: UUID,
        user_id: UUID | None,
    ) -> set[UUID]:
        if user_id is None:
            return set()

        user = db.get(User, user_id)
        if user is None or not user.enabled or user.tenant_id != tenant_id:
            return set()

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
            return False

        user = db.get(User, user_id)
        if user is None or not user.enabled or user.tenant_id != tenant_id:
            return False

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

    def can_access_chunk(
        self,
        db: Session,
        tenant_id: UUID,
        user_id: UUID,
        chunk_id: UUID,
    ) -> bool:
        accessible_sources = self.get_accessible_data_source_ids(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if not accessible_sources:
            return False

        statement = (
            select(DocumentChunk.id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(DataSource, DataSource.id == Document.data_source_id)
            .where(DocumentChunk.id == chunk_id)
            .where(DocumentChunk.tenant_id == tenant_id)
            .where(Document.tenant_id == tenant_id)
            .where(DataSource.tenant_id == tenant_id)
            .where(DataSource.id.in_(accessible_sources))
            .limit(1)
        )
        return db.scalar(statement) is not None