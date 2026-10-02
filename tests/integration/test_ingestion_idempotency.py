from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.services.document_service import DocumentService
from apps.worker.services.chunk_service import ChunkService
from apps.worker.services.embedding_service import EmbeddingService
from apps.worker.services.ingestion_service import IngestionService
from packages.domain.database import engine
from packages.domain.models import (
    ChunkEmbedding,
    DataSource,
    Document,
    DocumentChunk,
    DocumentVersion,
    Entity,
    EntityMention,
    EntityRelationship,
    IngestionJob,
    IngestionStatus,
    Tenant,
)
from packages.ingestion.chunker import DocumentChunker
from packages.ingestion.parser_registry import ParserRegistry
from packages.llm.embeddings import EmbeddingResult
from packages.retrieval.graph_extraction import (
    ExtractedEntity,
    ExtractedRelationship,
    GraphExtractionResult,
)
from packages.retrieval.graph_service import GraphService


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class DeterministicEmbeddingProvider:
    model_name = "idempotency-test-model"
    model_version = "1"
    dimensions = 1024

    def embed(self, text: str) -> EmbeddingResult:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        return [
            EmbeddingResult(
                vector=[0.1] * self.dimensions,
                model=self.model_name,
                version=self.model_version,
            )
            for _ in texts
        ]


class DeterministicGraphExtractor:
    extraction = GraphExtractionResult(
        entities=[
            ExtractedEntity(
                name="Payment Service",
                entity_type="SERVICE",
                mention_text="Payment Service",
            ),
            ExtractedEntity(
                name="Redis",
                entity_type="TECHNOLOGY",
                mention_text="Redis",
            ),
        ],
        relationships=[
            ExtractedRelationship(
                source_entity="Payment Service",
                target_entity="Redis",
                relationship_type="USES",
                confidence=1.0,
            )
        ],
    )

    def __init__(self, **kwargs) -> None:
        pass

    def extract(self, text: str) -> GraphExtractionResult:
        return self.extraction


def _record_counts(
    db: Session,
    tenant_id,
    document_version_id,
) -> dict[str, int]:
    chunk_ids = select(DocumentChunk.id).where(
        DocumentChunk.document_version_id == document_version_id
    )

    return {
        "chunks": db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_version_id == document_version_id
            )
        ),
        "embeddings": db.scalar(
            select(func.count()).select_from(ChunkEmbedding).where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.chunk_id.in_(chunk_ids),
            )
        ),
        "entities": db.scalar(
            select(func.count()).select_from(Entity).where(
                Entity.tenant_id == tenant_id,
                Entity.canonical_name.in_(
                    ["Payment Service", "Redis"]
                ),
            )
        ),
        "mentions": db.scalar(
            select(func.count()).select_from(EntityMention).where(
                EntityMention.tenant_id == tenant_id,
                EntityMention.chunk_id.in_(chunk_ids),
            )
        ),
        "relationships": db.scalar(
            select(func.count()).select_from(EntityRelationship).where(
                EntityRelationship.tenant_id == tenant_id,
                EntityRelationship.source_chunk_id.in_(chunk_ids),
            )
        ),
    }


def test_ingestion_and_derived_records_are_idempotent(monkeypatch) -> None:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        tenant = Tenant(name=f"idempotency-test-{uuid4()}")
        db.add(tenant)
        db.flush()

        data_source = DataSource(
            tenant_id=tenant.id,
            name="Engineering",
            source_type="test",
        )
        db.add(data_source)
        db.flush()

        storage = MemoryStorage()
        document_service = DocumentService(db=db, storage=storage)
        content = b"Payment Service uses Redis."
        document, version, job = document_service.create_document(
            tenant_id=tenant.id,
            data_source_id=data_source.id,
            filename="engineering.txt",
            mime_type="text/plain",
            content=content,
        )

        with pytest.raises(
            ValueError,
            match="identical document version already exists",
        ):
            document_service.create_document(
                tenant_id=tenant.id,
                data_source_id=data_source.id,
                filename="engineering.txt",
                mime_type="text/plain",
                content=content,
            )

        version_count = db.scalar(
            select(func.count()).select_from(DocumentVersion).where(
                DocumentVersion.document_id == document.id
            )
        )
        assert version_count == 1

        changed_document, changed_version, _ = (
            document_service.create_document(
                tenant_id=tenant.id,
                data_source_id=data_source.id,
                filename="engineering.txt",
                mime_type="text/plain",
                content=b"Payment Service uses Redis with failover.",
            )
        )
        assert changed_document.id == document.id
        assert changed_version.id != version.id
        assert changed_version.version_number == 2

        original_persist = GraphService.persist_extraction
        failure_state = {"injected": False}

        def persist_then_fail_once(service, *args, **kwargs) -> None:
            original_persist(service, *args, **kwargs)
            if not failure_state["injected"]:
                failure_state["injected"] = True
                raise RuntimeError("injected graph persistence failure")

        monkeypatch.setattr(
            "apps.worker.services.ingestion_service.OllamaGraphExtractor",
            DeterministicGraphExtractor,
        )
        monkeypatch.setattr(
            GraphService,
            "persist_extraction",
            persist_then_fail_once,
        )

        provider = DeterministicEmbeddingProvider()
        embedding_service = EmbeddingService(db=db, provider=provider)
        ingestion_service = IngestionService(
            db=db,
            storage=storage,
            parser_registry=ParserRegistry(),
            chunker=DocumentChunker(),
            chunk_service=ChunkService(db=db),
            embedding_service=embedding_service,
        )

        with pytest.raises(
            RuntimeError,
            match="injected graph persistence failure",
        ):
            ingestion_service.process_job(job.id)

        assert _record_counts(db, tenant.id, version.id) == {
            "chunks": 0,
            "embeddings": 0,
            "entities": 0,
            "mentions": 0,
            "relationships": 0,
        }

        ingestion_service.process_job(job.id)
        db.refresh(job)
        assert job.status == IngestionStatus.COMPLETED

        counts_after_success = _record_counts(
            db,
            tenant.id,
            version.id,
        )
        assert counts_after_success == {
            "chunks": 1,
            "embeddings": 1,
            "entities": 2,
            "mentions": 2,
            "relationships": 1,
        }

        ingestion_service.process_job(job.id)
        counts_after_reprocessing = _record_counts(
            db,
            tenant.id,
            version.id,
        )
        assert counts_after_reprocessing == counts_after_success

        chunk = db.scalar(
            select(DocumentChunk).where(
                DocumentChunk.document_version_id == version.id
            )
        )
        embedding_service.embed_chunks(
            tenant_id=tenant.id,
            chunks=[chunk],
        )
        db.flush()
        embedding_service.embed_chunks(
            tenant_id=tenant.id,
            chunks=[chunk],
        )
        db.flush()
        assert _record_counts(db, tenant.id, version.id)["embeddings"] == 1

        graph_service = GraphService()
        graph_service.persist_extraction(
            db=db,
            tenant_id=tenant.id,
            chunk_id=chunk.id,
            extraction=DeterministicGraphExtractor.extraction,
        )
        db.flush()
        graph_counts_after_first = _record_counts(
            db,
            tenant.id,
            version.id,
        )
        graph_service.persist_extraction(
            db=db,
            tenant_id=tenant.id,
            chunk_id=chunk.id,
            extraction=DeterministicGraphExtractor.extraction,
        )
        db.flush()
        graph_counts_after_second = _record_counts(
            db,
            tenant.id,
            version.id,
        )
        assert graph_counts_after_second == graph_counts_after_first
    finally:
        db.close()
        transaction.rollback()
        connection.close()