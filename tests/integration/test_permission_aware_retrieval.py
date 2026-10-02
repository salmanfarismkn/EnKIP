from uuid import uuid4

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from packages.domain.database import engine
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
from packages.llm.embeddings import EmbeddingResult
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.vector_search import VectorSearchService


class StubEmbeddingProvider:
    model_name = "permission-test-model"
    model_version = "1"
    dimensions = 1024

    def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[1.0] + [0.0] * 1023,
            model=self.model_name,
            version=self.model_version,
        )


def _document_ids(results: list[dict]) -> set:
    return {result["document_id"] for result in results}


def test_permission_aware_vector_lexical_and_graph_retrieval() -> None:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)

    try:
        tenant = Tenant(name=f"permission-test-{uuid4()}")
        db.add(tenant)
        db.flush()

        alice = User(
            tenant_id=tenant.id,
            email=f"alice-{uuid4()}@example.test",
            display_name="Alice",
        )
        bob = User(
            tenant_id=tenant.id,
            email=f"bob-{uuid4()}@example.test",
            display_name="Bob",
        )
        unassigned_user = User(
            tenant_id=tenant.id,
            email=f"unassigned-{uuid4()}@example.test",
            display_name="No Access",
        )
        engineering = DataSource(
            tenant_id=tenant.id,
            name="Engineering",
            source_type="test",
        )
        hr = DataSource(
            tenant_id=tenant.id,
            name="HR",
            source_type="test",
        )
        db.add_all([alice, bob, unassigned_user, engineering, hr])
        db.flush()

        db.add_all(
            [
                DataSourceAccess(
                    tenant_id=tenant.id,
                    user_id=alice.id,
                    data_source_id=engineering.id,
                ),
                DataSourceAccess(
                    tenant_id=tenant.id,
                    user_id=bob.id,
                    data_source_id=hr.id,
                ),
            ]
        )

        engineering_document = Document(
            tenant_id=tenant.id,
            data_source_id=engineering.id,
            title="engineering.txt",
            mime_type="text/plain",
            object_key=f"test/{uuid4()}/engineering.txt",
        )
        hr_document = Document(
            tenant_id=tenant.id,
            data_source_id=hr.id,
            title="hr.txt",
            mime_type="text/plain",
            object_key=f"test/{uuid4()}/hr.txt",
        )
        db.add_all([engineering_document, hr_document])
        db.flush()

        engineering_version = DocumentVersion(
            document_id=engineering_document.id,
            version_number=1,
            checksum=uuid4().hex,
        )
        hr_version = DocumentVersion(
            document_id=hr_document.id,
            version_number=1,
            checksum=uuid4().hex,
        )
        db.add_all([engineering_version, hr_version])
        db.flush()

        engineering_text = "Payment Service uses Redis."
        hr_text = "Employee Alice received a salary adjustment."
        engineering_chunk = DocumentChunk(
            tenant_id=tenant.id,
            document_version_id=engineering_version.id,
            chunk_index=0,
            text=engineering_text,
        )
        hr_chunk = DocumentChunk(
            tenant_id=tenant.id,
            document_version_id=hr_version.id,
            chunk_index=0,
            text=hr_text,
        )
        db.add_all([engineering_chunk, hr_chunk])
        db.flush()

        db.execute(
            update(DocumentChunk)
            .where(DocumentChunk.id == engineering_chunk.id)
            .values(
                search_vector=func.to_tsvector(
                    "english",
                    engineering_text,
                )
            )
        )
        db.execute(
            update(DocumentChunk)
            .where(DocumentChunk.id == hr_chunk.id)
            .values(
                search_vector=func.to_tsvector("english", hr_text)
            )
        )

        db.add_all(
            [
                ChunkEmbedding(
                    tenant_id=tenant.id,
                    chunk_id=engineering_chunk.id,
                    model_name=StubEmbeddingProvider.model_name,
                    model_version=StubEmbeddingProvider.model_version,
                    dimensions=StubEmbeddingProvider.dimensions,
                    embedding=[1.0] + [0.0] * 1023,
                ),
                ChunkEmbedding(
                    tenant_id=tenant.id,
                    chunk_id=hr_chunk.id,
                    model_name=StubEmbeddingProvider.model_name,
                    model_version=StubEmbeddingProvider.model_version,
                    dimensions=StubEmbeddingProvider.dimensions,
                    embedding=[1.0] + [0.0] * 1023,
                ),
            ]
        )

        payment_service = Entity(
            tenant_id=tenant.id,
            canonical_name="Payment Service",
            entity_type="service",
        )
        redis = Entity(
            tenant_id=tenant.id,
            canonical_name="Redis",
            entity_type="technology",
        )
        employee = Entity(
            tenant_id=tenant.id,
            canonical_name="Employee Alice",
            entity_type="person",
        )
        salary_adjustment = Entity(
            tenant_id=tenant.id,
            canonical_name="salary adjustment",
            entity_type="event",
        )
        db.add_all(
            [payment_service, redis, employee, salary_adjustment]
        )
        db.flush()

        db.add_all(
            [
                EntityRelationship(
                    tenant_id=tenant.id,
                    source_entity_id=payment_service.id,
                    target_entity_id=redis.id,
                    relationship_type="uses",
                    source_chunk_id=engineering_chunk.id,
                    confidence=1.0,
                ),
                EntityRelationship(
                    tenant_id=tenant.id,
                    source_entity_id=employee.id,
                    target_entity_id=salary_adjustment.id,
                    relationship_type="received",
                    source_chunk_id=hr_chunk.id,
                    confidence=1.0,
                ),
            ]
        )
        db.flush()

        embedding_provider = StubEmbeddingProvider()
        backends = {
            "vector": VectorSearchService(
                db=db,
                embedding_provider=embedding_provider,
            ).search,
            "lexical": LexicalSearchService(db=db).search,
            "graph": GraphSearchService().search,
        }

        for backend_name, search in backends.items():
            alice_engineering_results = search(
                db=db,
                tenant_id=tenant.id,
                user_id=alice.id,
                query="Payment Service uses Redis",
                limit=10,
            )
            bob_hr_results = search(
                db=db,
                tenant_id=tenant.id,
                user_id=bob.id,
                query="Employee Alice salary adjustment",
                limit=10,
            )
            alice_hr_results = search(
                db=db,
                tenant_id=tenant.id,
                user_id=alice.id,
                query="Employee Alice salary adjustment",
                limit=10,
            )
            bob_engineering_results = search(
                db=db,
                tenant_id=tenant.id,
                user_id=bob.id,
                query="Payment Service uses Redis",
                limit=10,
            )
            no_access_results = search(
                db=db,
                tenant_id=tenant.id,
                user_id=unassigned_user.id,
                query="Payment Service uses Redis",
                limit=10,
            )

            assert engineering_document.id in _document_ids(
                alice_engineering_results
            ), backend_name
            assert all(
                result["document_id"] != hr_document.id
                for result in alice_engineering_results
            ), backend_name
            assert hr_document.id in _document_ids(bob_hr_results), backend_name
            assert all(
                result["document_id"] != engineering_document.id
                for result in bob_hr_results
            ), backend_name
            assert all(
                result["document_id"] != hr_document.id
                for result in alice_hr_results
            ), backend_name
            assert all(
                result["document_id"] != engineering_document.id
                for result in bob_engineering_results
            ), backend_name
            assert no_access_results == [], backend_name
    finally:
        db.close()
        transaction.rollback()
        connection.close()