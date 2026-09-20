from fastapi.testclient import TestClient

from apps.api.main import app
from packages.domain.database import Base, engine


def test_project_is_initialized() -> None:
    assert True


def test_tenant_creation_works() -> None:
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        response = client.post("/tenants", json={"name": "Acme Engineering"})

    assert response.status_code == 201
    assert response.json()["name"] == "Acme Engineering"
    assert response.json()["id"]