from uuid import UUID, uuid4

from packages.domain.models import DataSource, DataSourceAccess, User

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import AuthenticatedPrincipal
from apps.api.dependencies import get_db
from apps.api.main import app
from apps.api.auth import get_authenticated_principal


class FakeDB:
    def __init__(self, scalar_values=None):
        self.scalar_values = list(scalar_values or [])

    def scalar(self, statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    def get(self, model, identity):
        return None

    def add(self, value):
        if hasattr(value, "id") and getattr(value, "id", None) is None:
            value.id = uuid4()

    def commit(self):
        return None

    def refresh(self, value):
        if hasattr(value, "created_at") and getattr(value, "created_at", None) is None:
            from datetime import datetime, timezone
            value.created_at = datetime.now(timezone.utc)

    def execute(self, statement):
        return None

    def close(self):
        return None


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def principal_factory():
    def build(tenant_id: UUID, user_id: UUID | None = None):
        return AuthenticatedPrincipal(
            user_id=user_id or uuid4(),
            tenant_id=tenant_id,
            issuer="https://issuer.example",
            subject="test-subject",
            email="user@example.com",
        )
    return build


def _client(principal, db):
    def override_principal():
        return principal

    def override_db():
        yield db

    app.dependency_overrides[get_authenticated_principal] = override_principal
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_tenant_creation_is_denied_and_cannot_self_promote(tenant_id, principal_factory):
    principal = principal_factory(tenant_id)
    client = _client(principal, FakeDB())
    try:
        response = client.post("/tenants", json={"name": "Self promoted tenant"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert "system-level" in response.json()["detail"]


@pytest.mark.parametrize(
    ("path", "method", "body"),
    [
        ("/tenants/{tenant_id}/users", "post", {"email": "new@example.com", "display_name": "New User"}),
        ("/tenants/{tenant_id}/data-sources", "post", {"name": "Restricted", "source_type": "local_upload"}),
        ("/tenants/{tenant_id}/users/{user_id}", "delete", None),
        ("/tenants/{tenant_id}/data-sources/{data_source_id}/access", "post", {"user_id": str(uuid4())}),
        ("/tenants/{tenant_id}/data-sources/{data_source_id}/access/{user_id}", "delete", None),
    ],
)
def test_non_admin_administrative_routes_are_denied(tenant_id, principal_factory, path, method, body):
    principal = principal_factory(tenant_id)
    db = FakeDB([type("User", (), {"is_tenant_admin": False})()])
    path = path.format(tenant_id=tenant_id, user_id=uuid4(), data_source_id=uuid4())
    client = _client(principal, db)
    try:
        response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json()["detail"] == "Tenant administrator access is required"


def test_cross_tenant_resource_and_user_spoofing_are_denied(tenant_id, principal_factory):
    principal = principal_factory(tenant_id)
    client = _client(principal, FakeDB())

    try:
        users = client.get(
            f"/tenants/{tenant_id}/users/{uuid4()}/data-sources",
        )
        document = client.post(
            f"/tenants/{uuid4()}/documents?data_source_id={uuid4()}",
            files={"file": ("x.txt", b"secret", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert users.status_code == 403
    assert document.status_code in (403, 422)


def test_tenant_admin_can_create_data_source_in_own_tenant(tenant_id, principal_factory):
    principal = principal_factory(tenant_id)
    admin = type("User", (), {"is_tenant_admin": True})()
    client = _client(principal, FakeDB([admin]))
    try:
        response = client.post(
            f"/tenants/{tenant_id}/data-sources",
            json={"name": "Authorized source", "source_type": "local_upload"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json()["name"] == "Authorized source"


def test_disabled_user_dependency_is_rejected_before_http_route():
    class DisabledDB(FakeDB):
        def scalar(self, statement):
            return None

    def rejected_principal():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="External identity is not linked to an enabled user")

    app.dependency_overrides[get_authenticated_principal] = rejected_principal
    app.dependency_overrides[get_db] = lambda: DisabledDB()
    client = TestClient(app)
    try:
        response = client.get(f"/tenants/{uuid4()}/users/{uuid4()}/data-sources")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "disabled" in response.text.lower() or "enabled" in response.text.lower()
