from pathlib import Path

from packages.domain.database import SessionLocal
from packages.ingestion.local_storage import LocalObjectStorage
from packages.ingestion.parser_registry import ParserRegistry


def process_job(job_id: str) -> None:
    from uuid import UUID

    from apps.worker.services.ingestion_service import (
        IngestionService,
    )

    db = SessionLocal()

    try:
        storage = LocalObjectStorage(
            root=Path("data"),
        )

        parser_registry = ParserRegistry()

        service = IngestionService(
            db=db,
            storage=storage,
            parser_registry=parser_registry,
        )

        service.process_job(UUID(job_id))

    finally:
        db.close()


def main() -> None:
    print("Enterprise Knowledge Platform Worker")


if __name__ == "__main__":
    main()