import threading
from uuid import uuid4

import requests

import apps.worker.main as worker_main
from apps.api.routes.health import live, ready
from apps.worker.services.ingestion_service import IngestionService


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _Queue:
    def __init__(self, job_id) -> None:
        self.job_id = job_id
        self.recovered = False

    def recover_stale_jobs(self, db) -> int:
        self.recovered = True
        return 0

    def claim_next(self, db):
        return self.job_id


def test_worker_finish_claimed_job_before_shutdown(monkeypatch) -> None:
    stop_event = threading.Event()
    job_id = uuid4()
    session = _Session()
    fake_queue = _Queue(job_id)
    processed: list[str] = []

    monkeypatch.setattr(worker_main, "queue", fake_queue)
    monkeypatch.setattr(worker_main, "SessionLocal", lambda: session)

    def process_job(processed_job_id: str) -> None:
        processed.append(processed_job_id)
        stop_event.set()

    monkeypatch.setattr(worker_main, "process_job", process_job)

    worker_main.run_worker(
        stop_event=stop_event,
        poll_interval_seconds=0.01,
    )

    assert processed == [str(job_id)]
    assert fake_queue.recovered
    assert session.closed


def test_ingestion_failure_categories_are_safe_and_actionable() -> None:
    assert (
        IngestionService._failure_category(requests.Timeout("slow model"))
        == "ollama_timeout"
    )
    assert (
        IngestionService._failure_category(
            requests.ConnectionError("connection failed")
        )
        == "ollama_unavailable"
    )
    assert (
        IngestionService._safe_failure_detail(
            "source_integrity",
            RuntimeError("checksum mismatch secret-source detail"),
        )
        == "source_integrity: source checksum mismatch"
    )


def test_live_is_independent_of_database() -> None:
    assert live() == {"status": "ok"}


def test_ready_is_503_when_database_check_fails() -> None:
    class _UnavailableSession:
        def execute(self, statement) -> None:
            raise RuntimeError("database connection failed")

        def rollback(self) -> None:
            pass

    response = ready(db=_UnavailableSession())  # type: ignore[arg-type]

    assert response.status_code == 503
    assert response.body == (
        b'{"status":"not_ready","database":"unavailable"}'
    )
