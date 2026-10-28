"""bind ingestion jobs to immutable document-version sources

Revision ID: 2c28e0a1f48d
Revises: a8fd8271c5d9
Create Date: 2026-10-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c28e0a1f48d"
down_revision: Union[str, Sequence[str], None] = "a8fd8271c5d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("source_object_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("source_mime_type", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("expected_checksum", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE document_versions AS version
        SET source_object_key =
            'tenant/' || document.tenant_id::text ||
            '/documents/' || document.id::text ||
            '/versions/' || version.id::text || '/source'
        FROM documents AS document
        WHERE version.document_id = document.id
          AND version.version_number = (
              SELECT MAX(latest.version_number)
              FROM document_versions AS latest
              WHERE latest.document_id = document.id
          )
          AND document.object_key =
              'tenant/' || document.tenant_id::text ||
              '/documents/' || document.id::text ||
              '/versions/' || version.id::text || '/source'
        """
    )
    op.execute(
        """
        UPDATE ingestion_jobs AS job
        SET expected_checksum = version.checksum
        FROM document_versions AS version
        WHERE job.document_version_id = version.id
        """
    )

    op.alter_column(
        "ingestion_jobs",
        "expected_checksum",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_document_version_source_object_key",
        "document_versions",
        ["source_object_key"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_document_version_source_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.checksum IS DISTINCT FROM OLD.checksum THEN
                RAISE EXCEPTION
                    'document version checksum is immutable';
            END IF;

            IF OLD.source_object_key IS NOT NULL
               AND NEW.source_object_key
                   IS DISTINCT FROM OLD.source_object_key THEN
                RAISE EXCEPTION
                    'document version source object is immutable';
            END IF;

            IF OLD.source_mime_type IS NOT NULL
               AND NEW.source_mime_type
                   IS DISTINCT FROM OLD.source_mime_type THEN
                RAISE EXCEPTION
                    'document version source MIME type is immutable';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_version_source_immutable
        BEFORE UPDATE OF checksum, source_object_key, source_mime_type
        ON document_versions
        FOR EACH ROW
        EXECUTE FUNCTION prevent_document_version_source_change()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_ingestion_job_source_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.document_version_id
                   IS DISTINCT FROM OLD.document_version_id
               OR NEW.expected_checksum
                   IS DISTINCT FROM OLD.expected_checksum THEN
                RAISE EXCEPTION
                    'ingestion job source identity is immutable';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ingestion_job_source_immutable
        BEFORE UPDATE OF document_version_id, expected_checksum
        ON ingestion_jobs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_ingestion_job_source_change()
        """
    )


def downgrade() -> None:
    has_jobs = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM ingestion_jobs)")
    ).scalar_one()
    has_sources = op.get_bind().execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM document_versions
                WHERE source_object_key IS NOT NULL
                   OR source_mime_type IS NOT NULL
            )
            """
        )
    ).scalar_one()
    if has_jobs or has_sources:
        raise RuntimeError(
            "Cannot downgrade version-source metadata while ingestion "
            "jobs or version source references exist; stop workers and "
            "perform an explicitly reviewed data migration first"
        )

    op.execute(
        """
        DROP TRIGGER IF EXISTS ingestion_job_source_immutable
        ON ingestion_jobs
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_ingestion_job_source_change()"
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS document_version_source_immutable
        ON document_versions
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_document_version_source_change()"
    )
    op.drop_constraint(
        "uq_document_version_source_object_key",
        "document_versions",
        type_="unique",
    )
    op.drop_column("ingestion_jobs", "expected_checksum")
    op.drop_column("document_versions", "source_mime_type")
    op.drop_column("document_versions", "source_object_key")
