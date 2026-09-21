from uuid import UUID

from sqlalchemy.orm import Session

from packages.domain.models import DataSource, DataSourceType


class DataSourceService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        tenant_id: UUID,
        name: str,
        source_type: DataSourceType,
    ) -> DataSource:
        data_source = DataSource(
            tenant_id=tenant_id,
            name=name,
            source_type=source_type,
        )

        self._db.add(data_source)
        self._db.commit()
        self._db.refresh(data_source)

        return data_source