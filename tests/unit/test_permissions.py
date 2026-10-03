from uuid import uuid4
from unittest.mock import Mock

from packages.permissions.service import PermissionService


def test_missing_user_uses_tenant_sources_when_access_is_unconfigured() -> None:
    tenant_id = uuid4()
    source_ids = {uuid4(), uuid4()}
    db = Mock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = list(source_ids)

    accessible = PermissionService().get_accessible_data_source_ids(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
    )

    assert accessible == source_ids


def test_missing_user_gets_no_sources_when_access_is_configured() -> None:
    db = Mock()
    db.scalar.return_value = uuid4()

    accessible = PermissionService().get_accessible_data_source_ids(
        db=db,
        tenant_id=uuid4(),
        user_id=None,
    )

    assert accessible == set()
    db.scalars.assert_not_called()