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
from packages.permissions.service import PermissionService
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
from packages.retrieval.vector_search import VectorSearchService


class StubEmbeddingProvider:
    model_name = "security-test-model"
    model_version = "1"
    dimensions = 1024

    def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            vector=[1.0] + [0.0] * 1023,
            model=self.model_name,
            version=self.model_version,
        )


class PassthroughReranker:
    def rerank(self, query: str, results: list[dict]) -> list[dict]:
        return results


def test_retrieval_respects_user_data_source_access() -> None:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)

    try:
        tenant = Tenant(name=f"security-test-{uuid4()}")
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
        db.add_all([alice, bob, engineering, hr])
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

        embedding = [1.0] + [0.0] * 1023
        db.add_all(
            [
                ChunkEmbedding(
                    tenant_id=tenant.id,
                    chunk_id=engineering_chunk.id,
                    model_name=StubEmbeddingProvider.model_name,
                    model_version=StubEmbeddingProvider.model_version,
                    dimensions=StubEmbeddingProvider.dimensions,
                    embedding=embedding,
                ),
                ChunkEmbedding(
                    tenant_id=tenant.id,
                    chunk_id=hr_chunk.id,
                    model_name=StubEmbeddingProvider.model_name,
                    model_version=StubEmbeddingProvider.model_version,
                    dimensions=StubEmbeddingProvider.dimensions,
                    embedding=embedding,
                ),
            ]
        )

        payment_entity = Entity(
            tenant_id=tenant.id,
            canonical_name="Payment Service",
            entity_type="service",
        )
        redis_entity = Entity(
            tenant_id=tenant.id,
            canonical_name="Redis",
            entity_type="technology",
        )
        salary_entity = Entity(
            tenant_id=tenant.id,
            canonical_name="salary adjustment",
            entity_type="event",
        )
        employee_entity = Entity(
            tenant_id=tenant.id,
            canonical_name="Employee Alice",
            entity_type="person",
        )
        db.add_all(
            [
                payment_entity,
                redis_entity,
                salary_entity,
                employee_entity,
            ]
        )
        db.flush()

        db.add_all(
            [
                EntityRelationship(
                    tenant_id=tenant.id,
                    source_entity_id=payment_entity.id,
                    target_entity_id=redis_entity.id,
                    relationship_type="uses",
                    source_chunk_id=engineering_chunk.id,
                    confidence=1.0,
                ),
                EntityRelationship(
                    tenant_id=tenant.id,
                    source_entity_id=employee_entity.id,
                    target_entity_id=salary_entity.id,
                    relationship_type="received",
                    source_chunk_id=hr_chunk.id,
                    confidence=1.0,
                ),
            ]
        )
        db.flush()

        hybrid_search = HybridSearchService(
            vector_search=VectorSearchService(
                db=db,
                embedding_provider=StubEmbeddingProvider(),
            ),
            lexical_search=LexicalSearchService(db=db),
            graph_search=GraphSearchService(),
            reranker=PassthroughReranker(),
            rrf=ReciprocalRankFusion(),
        )

        alice_payment = hybrid_search.search(
            db=db,
            tenant_id=tenant.id,
            user_id=alice.id,
            query="What does the Payment Service use?",
        )
        alice_salary = hybrid_search.search(
            db=db,
            tenant_id=tenant.id,
            user_id=alice.id,
            query="What salary adjustment did the employee receive?",
        )
        bob_salary = hybrid_search.search(
            db=db,
            tenant_id=tenant.id,
            user_id=bob.id,
            query="What salary adjustment did the employee receive?",
        )

        assert any("Payment Service uses Redis" in item["text"] for item in alice_payment)
        assert all("salary adjustment" not in item["text"].lower() for item in alice_salary)
        assert any("salary adjustment" in item["text"].lower() for item in bob_salary)

        permissions = PermissionService()
        assert permissions.get_accessible_data_source_ids(
            db,
            tenant.id,
            alice.id,
        ) == {engineering.id}
        assert permissions.get_accessible_data_source_ids(
            db,
            tenant.id,
            bob.id,
        ) == {hr.id}
    finally:
        db.close()
        transaction.rollback()
        connection.close()
