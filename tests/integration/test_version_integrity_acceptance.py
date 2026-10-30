from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from apps.api.services.document_service import DocumentService
from packages.domain.database import engine
from packages.domain.models import (
    DataSource,
    Document,
    DocumentVersion,
    IngestionJob,
    Tenant,
)


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        if key in self.objects:
            raise FileExistsError(key)
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def _create_tenant_and_source(db: Session) -> tuple[Tenant, DataSource]:
    tenant = Tenant(name=f"version-acceptance-{uuid4()}")
    db.add(tenant)
    db.flush()
    source = DataSource(
        tenant_id=tenant.id,
        name="source",
        source_type="test",
    )
    db.add(source)
    db.commit()
    return tenant, source


def test_concurrent_uploads_allocate_unique_ordered_versions() -> None:
    storage = MemoryStorage()
    with Session(engine, expire_on_commit=False) as setup_db:
        tenant, source = _create_tenant_and_source(setup_db)
        document, first_version, _ = DocumentService(
            setup_db,
            storage,
        ).create_document(
            tenant_id=tenant.id,
            data_source_id=source.id,
            filename="concurrent.txt",
            mime_type="text/plain",
            content=b"original content",
        )
        document_id = document.id

    barrier = Barrier(2)

    def create_version(content: bytes) -> tuple[int, str]:
        with Session(engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            _, version, _ = DocumentService(db, storage).create_document(
                tenant_id=tenant.id,
                data_source_id=source.id,
                filename="concurrent.txt",
                mime_type="text/plain",
                content=content,
            )
            return version.version_number, version.source_object_key

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(
            executor.map(
                create_version,
                (b"concurrent content A", b"concurrent content B"),
            )
        )

    assert sorted(version_number for version_number, _ in created) == [2, 3]
    assert len({key for _, key in created}) == 2

    with Session(engine) as db:
        versions = list(
            db.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number)
            ).all()
        )
    assert [version.version_number for version in versions] == [1, 2, 3]
    assert versions[0].id == first_version.id


def test_storage_created_before_database_failure_leaves_no_job_or_version() -> None:
    storage = MemoryStorage()
    with Session(engine, expire_on_commit=False) as setup_db:
        tenant, source = _create_tenant_and_source(setup_db)
        document = Document(
            tenant_id=tenant.id,
            data_source_id=source.id,
            title="commit-failure.txt",
            mime_type="text/plain",
            object_key="pending",
        )
        setup_db.add(document)
        setup_db.commit()
        document_id = document.id

    content = b"orphaned object after commit failure"
    with Session(engine, expire_on_commit=False) as db:
        original_commit = db.commit

        def fail_commit() -> None:
            raise RuntimeError("injected database commit failure")

        db.commit = fail_commit
        with pytest.raises(
            RuntimeError,
            match="injected database commit failure",
        ):
            DocumentService(db, storage).create_document(
                tenant_id=tenant.id,
                data_source_id=source.id,
                filename="commit-failure.txt",
                mime_type="text/plain",
                content=content,
            )
        db.commit = original_commit
        db.rollback()

    with Session(engine) as db:
        assert db.scalar(
            select(func.count()).select_from(DocumentVersion).where(
                DocumentVersion.document_id == document_id
            )
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(IngestionJob).where(
                IngestionJob.tenant_id == tenant.id
            )
        ) == 0
        assert db.get(Document, document_id).object_key == "pending"

    assert len(storage.objects) == 0


def test_previous_revision_migration_preserves_records_and_backfills_safely(
    migration_schema,
) -> None:
    from sqlalchemy import create_engine

    migration_engine = create_engine(migration_schema)
    tenant_id = uuid4()
    source_id = uuid4()
    document_id = uuid4()
    version_a_id = uuid4()
    version_b_id = uuid4()
    job_a_id = uuid4()
    job_b_id = uuid4()
    ambiguous_document_id = uuid4()
    ambiguous_version_id = uuid4()
    ambiguous_job_id = uuid4()
    checksum_a = sha256(b"historical A").hexdigest()
    checksum_b = sha256(b"historical B").hexdigest()
    ambiguous_checksum = sha256(b"unknown historical object").hexdigest()
    version_b_key = (
        f"tenant/{tenant_id}/documents/{document_id}/"
        f"versions/{version_b_id}/source"
    )

    try:
        with migration_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
                {"id": tenant_id, "name": "migration-test"},
            )
            connection.execute(
                text(
                    "INSERT INTO data_sources "
                    "(id, tenant_id, name, source_type) "
                    "VALUES (:id, :tenant_id, :name, :source_type)"
                ),
                {
                    "id": source_id,
                    "tenant_id": tenant_id,
                    "name": "source",
                    "source_type": "test",
                },
            )
            for target_document_id, object_key in (
                (document_id, version_b_key),
                (ambiguous_document_id, "legacy/unverifiable-key"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO documents "
                        "(id, tenant_id, data_source_id, title, mime_type, object_key) "
                        "VALUES (:id, :tenant_id, :source_id, :title, "
                        ":mime_type, :object_key)"
                    ),
                    {
                        "id": target_document_id,
                        "tenant_id": tenant_id,
                        "source_id": source_id,
                        "title": str(target_document_id),
                        "mime_type": "text/plain",
                        "object_key": object_key,
                    },
                )

            for target_version_id, target_document_id, number, checksum in (
                (version_a_id, document_id, 1, checksum_a),
                (version_b_id, document_id, 2, checksum_b),
                (
                    ambiguous_version_id,
                    ambiguous_document_id,
                    1,
                    ambiguous_checksum,
                ),
            ):
                connection.execute(
                    text(
                        "INSERT INTO document_versions "
                        "(id, document_id, version_number, checksum, "
                        "processing_status) "
                        "VALUES (:id, :document_id, :number, :checksum, "
                        "'pending')"
                    ),
                    {
                        "id": target_version_id,
                        "document_id": target_document_id,
                        "number": number,
                        "checksum": checksum,
                    },
                )

            for target_job_id, target_version_id in (
                (job_a_id, version_a_id),
                (job_b_id, version_b_id),
                (ambiguous_job_id, ambiguous_version_id),
            ):
                connection.execute(
                    text(
                        "INSERT INTO ingestion_jobs "
                        "(id, tenant_id, document_version_id, status, "
                        "attempt_count, max_attempts) "
                        "VALUES (:id, :tenant_id, :version_id, 'pending', 0, 3)"
                    ),
                    {
                        "id": target_job_id,
                        "tenant_id": tenant_id,
                        "version_id": target_version_id,
                    },
                )

        from alembic import command
        from alembic.config import Config
        from apps.api.config import settings

        previous_url = settings.database_url
        settings.database_url = migration_schema.render_as_string(
            hide_password=False
        )
        try:
            command.upgrade(Config("alembic.ini"), "2c28e0a1f48d")
        finally:
            settings.database_url = previous_url

        with migration_engine.connect() as connection:
            versions = {
                row.id: row
                for row in connection.execute(
                    text(
                        "SELECT id, source_object_key, source_mime_type, "
                        "checksum FROM document_versions"
                    )
                )
            }
            jobs = {
                row.id: row
                for row in connection.execute(
                    text(
                        "SELECT id, document_version_id, expected_checksum, "
                        "status FROM ingestion_jobs"
                    )
                )
            }

        assert versions[version_a_id].source_object_key is None
        assert versions[version_a_id].source_mime_type is None
        assert versions[version_b_id].source_object_key == version_b_key
        assert versions[version_b_id].source_mime_type is None
        assert versions[ambiguous_version_id].source_object_key is None
        assert versions[ambiguous_version_id].source_mime_type is None
        assert jobs[job_a_id].document_version_id == version_a_id
        assert jobs[job_a_id].expected_checksum == checksum_a
        assert jobs[job_b_id].document_version_id == version_b_id
        assert jobs[job_b_id].expected_checksum == checksum_b
        assert jobs[ambiguous_job_id].document_version_id == (
            ambiguous_version_id
        )
        assert jobs[ambiguous_job_id].expected_checksum == ambiguous_checksum
        assert all(job.status == "pending" for job in jobs.values())

        with migration_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ingestion_jobs SET attempt_count = 1, "
                    "status = 'processing' WHERE id = :job_id"
                ),
                {"job_id": job_b_id},
            )

        with pytest.raises(DBAPIError):
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ingestion_jobs SET expected_checksum = :checksum "
                        "WHERE id = :job_id"
                    ),
                    {"checksum": checksum_a, "job_id": job_b_id},
                )

        with pytest.raises(DBAPIError):
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE document_versions SET checksum = :checksum "
                        "WHERE id = :version_id"
                    ),
                    {"checksum": checksum_a, "version_id": version_b_id},
                )

        from alembic import command
        from alembic.config import Config
        from apps.api.config import settings

        previous_url = settings.database_url
        settings.database_url = migration_schema.render_as_string(
            hide_password=False
        )
        try:
            with pytest.raises(
                RuntimeError,
                match="Cannot downgrade version-source metadata",
            ):
                command.downgrade(Config("alembic.ini"), "a8fd8271c5d9")
        finally:
            settings.database_url = previous_url

        with migration_engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT expected_checksum FROM ingestion_jobs "
                    "WHERE id = :job_id"
                ),
                {"job_id": job_b_id},
            ).scalar_one() == checksum_b
    finally:
        migration_engine.dispose()


def test_completed_source_identity_cannot_be_reassigned() -> None:
    storage = MemoryStorage()
    with Session(engine, expire_on_commit=False) as db:
        tenant, source = _create_tenant_and_source(db)
        _, version, job = DocumentService(db, storage).create_document(
            tenant_id=tenant.id,
            data_source_id=source.id,
            filename="immutable.txt",
            mime_type="text/plain",
            content=b"immutable source",
        )
        version_id = version.id
        job_id = job.id
        other_checksum = sha256(b"different").hexdigest()

        with pytest.raises(DBAPIError):
            version.checksum = other_checksum
            db.commit()
        db.rollback()

        with pytest.raises(DBAPIError):
            job.expected_checksum = other_checksum
            db.commit()
        db.rollback()

        assert db.get(DocumentVersion, version_id).checksum == (
            sha256(b"immutable source").hexdigest()
        )
        assert db.get(IngestionJob, job_id).expected_checksum == (
            sha256(b"immutable source").hexdigest()
        )


def test_auth_identity_migration_preserves_existing_users(migration_schema) -> None:
    from sqlalchemy import create_engine

    migration_engine = create_engine(migration_schema)
    tenant_id = uuid4()
    user_id = uuid4()

    try:
        with migration_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
                {"id": tenant_id, "name": "identity-migration-test"},
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, tenant_id, email, display_name) "
                    "VALUES (:id, :tenant_id, :email, :display_name)"
                ),
                {
                    "id": user_id,
                    "tenant_id": tenant_id,
                    "email": "existing@example.com",
                    "display_name": "Existing User",
                },
            )

        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")

        with migration_engine.connect() as connection:
            enabled = connection.execute(
                text("SELECT enabled FROM users WHERE id = :id"),
                {"id": user_id},
            ).scalar_one()
            mapping_count = connection.execute(
                text("SELECT count(*) FROM external_identities")
            ).scalar_one()
            is_tenant_admin = connection.execute(
                text("SELECT is_tenant_admin FROM users WHERE id = :id"),
                {"id": user_id},
            ).scalar_one()

        assert enabled is True
        assert is_tenant_admin is False
        assert mapping_count == 0
    finally:
        migration_engine.dispose()
