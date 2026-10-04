"""Synthetic fixtures for lexical retrieval development diagnostics."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.domain.models import (
    DataSource,
    DataSourceAccess,
    Document,
    DocumentChunk,
    DocumentVersion,
    Tenant,
    User,
)


TENANT_ID = UUID("f1000000-0000-4000-8000-000000000001")
ALICE_ID = UUID("f2000000-0000-4000-8000-000000000001")
BOB_ID = UUID("f2000000-0000-4000-8000-000000000002")
AUTHORIZED_SOURCE_ID = UUID("f3000000-0000-4000-8000-000000000001")
RESTRICTED_SOURCE_ID = UUID("f3000000-0000-4000-8000-000000000002")

ALLOWED_SOURCES_BY_USER = {
    ALICE_ID: {AUTHORIZED_SOURCE_ID},
    BOB_ID: {RESTRICTED_SOURCE_ID},
}

DEVELOPMENT_DOCUMENTS = [
    {
        "id": UUID("f4000000-0000-4000-8000-000000000001"),
        "source_id": AUTHORIZED_SOURCE_ID,
        "title": "Helium lattice process.txt",
        "chunks": [
            "Helium lattice annealing stabilizes zircon grain boundaries "
            "at 850 degrees Celsius.",
            "The second stage measures phase shift after the thermal cycle "
            "and records changes in grain size.",
        ],
    },
    {
        "id": UUID("f4000000-0000-4000-8000-000000000002"),
        "source_id": AUTHORIZED_SOURCE_ID,
        "title": "PX controller maintenance.txt",
        "chunks": [
            "Controller PX-410B emits fault 7A-2 after silicon wafer "
            "calibration. Replace the ceramic fuse before restarting. "
            "Telemetry channel CLK_96Hz logs the controller clock state."
        ],
    },
    {
        "id": UUID("f4000000-0000-4000-8000-000000000003"),
        "source_id": AUTHORIZED_SOURCE_ID,
        "title": "Ridge mineral assay.txt",
        "chunks": [
            "Luminous calcite was catalogued beneath the western ridge. "
            "Field notes describe its pale surface and location.",
            "The quartz feldspar assay measured boron traces in the sealed "
            "sample from the eastern cut.",
        ],
    },
    {
        "id": UUID("f4000000-0000-4000-8000-000000000004"),
        "source_id": RESTRICTED_SOURCE_ID,
        "title": "Umbra audit memorandum.txt",
        "chunks": [
            "Umbra payroll ciphertext audit uses marker QZ-88 to verify "
            "restricted ledger access. This is synthetic test material.",
        ],
    },
]


@dataclass(frozen=True)
class DevelopmentCorpus:
    document_context: dict[UUID, tuple[UUID, UUID]]
    allowed_sources_by_user: dict[UUID, set[UUID]]


def seed_development_corpus(db: Session) -> DevelopmentCorpus:
    """Create fixed synthetic rows; the caller must roll back its transaction."""
    if db.scalar(select(Tenant.id).where(Tenant.id == TENANT_ID)) is not None:
        raise RuntimeError(
            "Development tenant ID already exists; refusing to modify it."
        )

    db.add(Tenant(id=TENANT_ID, name="Lexical development synthetic tenant"))
    db.add_all(
        [
            User(
                id=ALICE_ID,
                tenant_id=TENANT_ID,
                email="lexdev-alice@example.test",
                display_name="Synthetic Alice",
            ),
            User(
                id=BOB_ID,
                tenant_id=TENANT_ID,
                email="lexdev-bob@example.test",
                display_name="Synthetic Bob",
            ),
            DataSource(
                id=AUTHORIZED_SOURCE_ID,
                tenant_id=TENANT_ID,
                name="Lexical development authorized source",
                source_type="test",
            ),
            DataSource(
                id=RESTRICTED_SOURCE_ID,
                tenant_id=TENANT_ID,
                name="Lexical development restricted source",
                source_type="test",
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            DataSourceAccess(
                tenant_id=TENANT_ID,
                user_id=ALICE_ID,
                data_source_id=AUTHORIZED_SOURCE_ID,
            ),
            DataSourceAccess(
                tenant_id=TENANT_ID,
                user_id=BOB_ID,
                data_source_id=RESTRICTED_SOURCE_ID,
            ),
        ]
    )

    document_context = {}
    for document_data in DEVELOPMENT_DOCUMENTS:
        document = Document(
            id=document_data["id"],
            tenant_id=TENANT_ID,
            data_source_id=document_data["source_id"],
            title=document_data["title"],
            mime_type="text/plain",
            object_key=f"lexdev/{document_data['id']}.txt",
        )
        db.add(document)
        db.flush()

        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            checksum=document.id.hex,
            extracted_text="\n\n".join(document_data["chunks"]),
        )
        db.add(version)
        db.flush()

        for chunk_index, chunk_text in enumerate(document_data["chunks"]):
            db.add(
                DocumentChunk(
                    tenant_id=TENANT_ID,
                    document_version_id=version.id,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    token_count=len(chunk_text.split()),
                )
            )
            db.flush()

        document_context[document.id] = (
            TENANT_ID,
            document_data["source_id"],
        )

    db.flush()
    return DevelopmentCorpus(
        document_context=document_context,
        allowed_sources_by_user=ALLOWED_SOURCES_BY_USER,
    )