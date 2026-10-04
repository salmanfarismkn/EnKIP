"""Deterministic synthetic corpus for held-out retrieval evaluation."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from packages.domain.models import (
    ChunkEmbedding,
    DataSource,
    DataSourceAccess,
    Document,
    DocumentChunk,
    DocumentVersion,
    Entity,
    EntityRelationship,
    Tenant,
    User,
)


TENANT_A_ID = UUID("e1000000-0000-4000-8000-000000000001")
TENANT_B_ID = UUID("e1000000-0000-4000-8000-000000000002")
USER_A_ID = UUID("e2000000-0000-4000-8000-000000000001")
USER_B_ID = UUID("e2000000-0000-4000-8000-000000000002")
SOURCE_A_ID = UUID("e3000000-0000-4000-8000-000000000001")
SOURCE_RESTRICTED_ID = UUID("e3000000-0000-4000-8000-000000000002")
SOURCE_B_ID = UUID("e3000000-0000-4000-8000-000000000003")

ALLOWED_SOURCES_BY_USER = {
    USER_A_ID: {SOURCE_A_ID},
    USER_B_ID: {SOURCE_B_ID},
}

SYNTHETIC_DOCUMENTS = [
    {
        "id": UUID("e4000000-0000-4000-8000-000000000001"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "Aurelia tide array maintenance.txt",
        "chunks": [
            "The Aurelia Tide Array converts coastal currents into power. "
            "Technicians inspect each tidal rotor blade every six weeks, "
            "measuring edge pitting, root movement, and seal wear.",
            "During spring tides, the Aurelia platform logs water velocity "
            "and rotor vibration every fifteen minutes. A rising vibration "
            "trend prompts a bearing review before the next scheduled visit.",
            "The maintenance ledger compares blade inspection notes with "
            "salinity sensor drift. Crews replace a damaged leading edge "
            "when two consecutive readings exceed the site's tolerance.",
        ],
        "entities": ("Aurelia Tide Array", "tidal rotor blades"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000002"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "Vesper porcelain firing notes.txt",
        "chunks": [
            "Vesper porcelain receives its cobalt glaze in a mildly reducing "
            "kiln atmosphere. The firing schedule holds at 1240 degrees "
            "Celsius for twenty minutes, then cools slowly to prevent blisters.",
        ],
        "entities": ("Vesper porcelain", "reducing kiln atmosphere"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000003"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "Nightjar migration observations.txt",
        "chunks": [
            "The nightjar count begins after dusk at the northern reed beds. "
            "Banding records show that most northbound movement starts in "
            "late April, after three evenings above twelve degrees.",
            "Observers compare departure dates with insect abundance and "
            "cloud cover. The southbound return is tracked separately in "
            "September and should not be combined with spring counts.",
        ],
        "entities": ("nightjar migration", "northern reed beds"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000004"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "Basalt tunnel acoustic survey.txt",
        "chunks": [
            "In the Basalt Ridge tunnel, a 38 kilohertz acoustic sweep "
            "reveals narrow fractures behind the support ribs. Surveyors "
            "repeat the pass at the same sensor spacing to separate cracks "
            "from echoes caused by drainage pipes.",
        ],
        "entities": ("Basalt Ridge tunnel", "38 kilohertz sweep"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000005"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "Selenic greenhouse thermal trial.txt",
        "chunks": [
            "The Selenic greenhouse uses a double water curtain to retain "
            "heat after sunset. In the winter trial, the inner growing bay "
            "stayed 4.2 degrees warmer than outside for seven hours.",
            "Thermal cameras recorded the west wall first because its "
            "aluminium frame loses heat more quickly. A closed curtain "
            "reduced overnight heating demand without raising humidity.",
            "The report distinguishes night heat retention from daytime "
            "light transmission. Ventilation tests were run on separate dates "
            "to avoid mixing the two measurements.",
        ],
        "entities": ("Selenic greenhouse", "double water curtain"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000006"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "Cryogenic rail brake inspection.txt",
        "chunks": [
            "Cryogenic rail cars require brake pad inspection every 800 "
            "operating hours. Technicians check for brittle lining, uneven "
            "wear, and condensation in the actuator housing before release.",
        ],
        "entities": ("cryogenic rail cars", "brake pad inspection"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000007"),
        "tenant_id": TENANT_B_ID,
        "source_id": SOURCE_B_ID,
        "title": "Fenwater estuary field study.txt",
        "chunks": [
            "Fenwater estuary plots showed that seagrass density increased "
            "where spring runoff lowered salinity below 27 parts per thousand.",
            "The survey sampled the eastern inlet at low tide. Turbidity "
            "peaked two days after rainfall, while the western plots changed "
            "little during the same observation period.",
        ],
        "entities": ("Fenwater estuary", "eastern seagrass plots"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000008"),
        "tenant_id": TENANT_B_ID,
        "source_id": SOURCE_B_ID,
        "title": "Lucent orbital tracker calibration.txt",
        "chunks": [
            "The Lucent orbital team realigns its star tracker against "
            "three reference stars after a radiation event. Calibration is "
            "accepted when the measured angular error falls below 0.04 degrees.",
        ],
        "entities": ("Lucent orbital team", "star tracker calibration"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000009"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_RESTRICTED_ID,
        "title": "Aurelia restricted maintenance draft.txt",
        "chunks": [
            "The Aurelia Tide Array restricted draft repeats the six-week "
            "tidal rotor blade inspection interval and describes seal wear "
            "observed during spring tides.",
            "This synthetic restricted note adds a quartz payroll marker "
            "used only to verify source-level access filtering.",
        ],
        "entities": ("Aurelia Tide Array", "tidal rotor blades"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000010"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_RESTRICTED_ID,
        "title": "Vesper restricted firing memo.txt",
        "chunks": [
            "A restricted Vesper porcelain memo confirms the reducing kiln "
            "atmosphere and cobalt glaze schedule described in the separate "
            "synthetic firing notes.",
        ],
        "entities": ("Vesper porcelain", "reducing kiln atmosphere"),
    },
    {
        "id": UUID("e4000000-0000-4000-8000-000000000011"),
        "tenant_id": TENANT_A_ID,
        "source_id": SOURCE_A_ID,
        "title": "General inspection vocabulary.txt",
        "chunks": [
            "Synthetic inspection reports may mention sensors, vibration, "
            "maintenance intervals, survey instruments, or seasonal trends. "
            "This index note contains no measurements for any named project.",
        ],
        "entities": ("synthetic inspection reports", "survey instruments"),
    },
]


@dataclass(frozen=True)
class SeededCorpus:
    document_context: dict[UUID, tuple[UUID, UUID]]
    allowed_sources_by_user: dict[UUID, set[UUID]]


def seed_heldout_corpus(db: Session, embedding_provider) -> SeededCorpus:
    """Insert a synthetic corpus into the caller's transaction."""
    tenant_ids = [TENANT_A_ID, TENANT_B_ID]
    existing = db.scalar(
        select(Tenant.id).where(Tenant.id.in_(tenant_ids)).limit(1)
    )
    if existing is not None:
        raise RuntimeError(
            "Held-out synthetic tenant IDs already exist; refusing to modify them."
        )

    tenant_a = Tenant(id=TENANT_A_ID, name="Held-out synthetic tenant A")
    tenant_b = Tenant(id=TENANT_B_ID, name="Held-out synthetic tenant B")
    db.add_all([tenant_a, tenant_b])
    db.add_all(
        [
            User(
                id=USER_A_ID,
                tenant_id=TENANT_A_ID,
                email="heldout-alice@example.test",
                display_name="Synthetic Alice",
            ),
            User(
                id=USER_B_ID,
                tenant_id=TENANT_B_ID,
                email="heldout-bob@example.test",
                display_name="Synthetic Bob",
            ),
        ]
    )
    db.add_all(
        [
            DataSource(
                id=SOURCE_A_ID,
                tenant_id=TENANT_A_ID,
                name="Synthetic public corpus A",
                source_type="test",
            ),
            DataSource(
                id=SOURCE_RESTRICTED_ID,
                tenant_id=TENANT_A_ID,
                name="Synthetic restricted corpus A",
                source_type="test",
            ),
            DataSource(
                id=SOURCE_B_ID,
                tenant_id=TENANT_B_ID,
                name="Synthetic public corpus B",
                source_type="test",
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            DataSourceAccess(
                tenant_id=TENANT_A_ID,
                user_id=USER_A_ID,
                data_source_id=SOURCE_A_ID,
            ),
            DataSourceAccess(
                tenant_id=TENANT_B_ID,
                user_id=USER_B_ID,
                data_source_id=SOURCE_B_ID,
            ),
        ]
    )

    all_chunks = [
        chunk
        for document in SYNTHETIC_DOCUMENTS
        for chunk in document["chunks"]
    ]
    embeddings = embedding_provider.embed_batch(all_chunks)
    embedding_index = 0
    entity_by_name: dict[tuple[UUID, str], Entity] = {}
    document_context: dict[UUID, tuple[UUID, UUID]] = {}

    for document_data in SYNTHETIC_DOCUMENTS:
        document = Document(
            id=document_data["id"],
            tenant_id=document_data["tenant_id"],
            data_source_id=document_data["source_id"],
            title=document_data["title"],
            mime_type="text/plain",
            object_key=f"heldout/{document_data['id']}.txt",
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

        first_chunk_id = None
        for chunk_index, chunk_text in enumerate(document_data["chunks"]):
            chunk = DocumentChunk(
                tenant_id=document_data["tenant_id"],
                document_version_id=version.id,
                chunk_index=chunk_index,
                text=chunk_text,
                token_count=len(chunk_text.split()),
            )
            db.add(chunk)
            db.flush()
            if first_chunk_id is None:
                first_chunk_id = chunk.id
            db.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk.id)
                .values(
                    search_vector=func.to_tsvector("english", chunk_text)
                )
            )

            embedding = embeddings[embedding_index]
            embedding_index += 1
            db.add(
                ChunkEmbedding(
                    tenant_id=document_data["tenant_id"],
                    chunk_id=chunk.id,
                    model_name=embedding.model,
                    model_version=embedding.version,
                    dimensions=embedding_provider.dimensions,
                    embedding=embedding.vector,
                )
            )

        graph_entities = []
        for name in document_data["entities"]:
            key = (document_data["tenant_id"], name)
            entity = entity_by_name.get(key)
            if entity is None:
                entity = Entity(
                    tenant_id=document_data["tenant_id"],
                    canonical_name=name,
                    entity_type="synthetic-topic",
                )
                db.add(entity)
                db.flush()
                entity_by_name[key] = entity
            graph_entities.append(entity)

        db.add(
            EntityRelationship(
                tenant_id=document_data["tenant_id"],
                source_entity_id=graph_entities[0].id,
                target_entity_id=graph_entities[1].id,
                relationship_type="describes",
                source_chunk_id=first_chunk_id,
                confidence=1.0,
            )
        )
        document_context[document.id] = (
            document_data["tenant_id"],
            document_data["source_id"],
        )

    db.flush()
    return SeededCorpus(
        document_context=document_context,
        allowed_sources_by_user=ALLOWED_SOURCES_BY_USER,
    )