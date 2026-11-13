from fastapi.testclient import TestClient

from apps.api.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "not_checked",
    }


def test_live_does_not_check_database() -> None:
    response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_dependency() -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
    }