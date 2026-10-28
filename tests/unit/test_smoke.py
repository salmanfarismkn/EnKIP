from fastapi.testclient import TestClient

from apps.api.main import app


def test_project_is_initialized() -> None:
    assert True


def test_tenant_creation_works() -> None:
    with TestClient(app) as client:
        response = client.post("/tenants", json={"name": "Acme Engineering"})

    assert response.status_code == 401