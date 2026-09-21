from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.domain.models import DataSourceType


class DataSourceCreate(BaseModel):
    name: str
    source_type: DataSourceType


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    source_type: DataSourceType