from uuid import uuid4

from sqlalchemy import func, select, text, update
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
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
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


def test_lexical_search_vector_gin_index_exists() -> None:
    with engine.connect() as connection:
        index_definition = connection.execute(
            text("""
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'document_chunks'
                  AND indexname = 'ix_document_chunks_search_vector'
            """)
        ).scalar_one_or_none()

    assert index_definition is not None
    assert "using gin (search_vector)" in index_definition.lower()


class NoGraphSearch:
    def search(self, **kwargs) -> list[dict]:
        return []


class PassthroughReranker:
    def rerank(self, query: str, results: list[dict]) -> list[dict]:
        return results


def _seed_search_document(
    db: Session,
    tenant_id,
    data_source_id,
    title: str,
    content: str,
    graph_entities: tuple[str, str],
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        data_source_id=data_source_id,
        title=title,
        mime_type="text/plain",
        object_key=f"test/{uuid4()}/{title}",
    )
    db.add(document)
    db.flush()

    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        checksum=uuid4().hex,
    )
    db.add(version)
    db.flush()

    chunk = DocumentChunk(
        tenant_id=tenant_id,
        document_version_id=version.id,
        chunk_index=0,
        text=content,
    )
    db.add(chunk)
    db.flush()
    db.execute(
        update(DocumentChunk)
        .where(DocumentChunk.id == chunk.id)
        .values(search_vector=func.to_tsvector("english", content))
    )
    db.add(
        ChunkEmbedding(
            tenant_id=tenant_id,
            chunk_id=chunk.id,
            model_name=StubEmbeddingProvider.model_name,
            model_version=StubEmbeddingProvider.model_version,
            dimensions=StubEmbeddingProvider.dimensions,
            embedding=[1.0] + [0.0] * 1023,
        )
    )

    entities = []
    for name in graph_entities:
        entity = db.scalar(
            select(Entity).where(
                Entity.tenant_id == tenant_id,
                Entity.canonical_name == name,
                Entity.entity_type == "test-concept",
            )
        )
        if entity is None:
            entity = Entity(
                tenant_id=tenant_id,
                canonical_name=name,
                entity_type="test-concept",
            )
            db.add(entity)
            db.flush()
        entities.append(entity)
    db.add(
        EntityRelationship(
            tenant_id=tenant_id,
            source_entity_id=entities[0].id,
            target_entity_id=entities[1].id,
            relationship_type="documents",
            source_chunk_id=chunk.id,
            confidence=1.0,
        )
    )
    db.flush()
    return document


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


def test_all_retrievers_enforce_source_and_tenant_permissions() -> None:
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, expire_on_commit=False)

    try:
        tenant = Tenant(name=f"heldout-security-{uuid4()}")
        foreign_tenant = Tenant(name=f"heldout-foreign-{uuid4()}")
        db.add_all([tenant, foreign_tenant])
        db.flush()

        alice = User(
            tenant_id=tenant.id,
            email=f"alice-{uuid4()}@example.test",
            display_name="Synthetic Alice",
        )
        bob = User(
            tenant_id=tenant.id,
            email=f"bob-{uuid4()}@example.test",
            display_name="Synthetic Bob",
        )
        carol = User(
            tenant_id=foreign_tenant.id,
            email=f"carol-{uuid4()}@example.test",
            display_name="Synthetic Carol",
        )
        authorized_source = DataSource(
            tenant_id=tenant.id,
            name="Synthetic authorized source",
            source_type="test",
        )
        restricted_source = DataSource(
            tenant_id=tenant.id,
            name="Synthetic restricted source",
            source_type="test",
        )
        foreign_source = DataSource(
            tenant_id=foreign_tenant.id,
            name="Synthetic foreign source",
            source_type="test",
        )
        db.add_all(
            [alice, bob, carol, authorized_source, restricted_source, foreign_source]
        )
        db.flush()
        db.add_all(
            [
                DataSourceAccess(
                    tenant_id=tenant.id,
                    user_id=alice.id,
                    data_source_id=authorized_source.id,
                ),
                DataSourceAccess(
                    tenant_id=tenant.id,
                    user_id=bob.id,
                    data_source_id=restricted_source.id,
                ),
                DataSourceAccess(
                    tenant_id=foreign_tenant.id,
                    user_id=carol.id,
                    data_source_id=foreign_source.id,
                ),
            ]
        )

        shared_terms = "Virelia cobalt ledger records for synthetic testing."
        authorized_document = _seed_search_document(
            db,
            tenant.id,
            authorized_source.id,
            "authorized-ledger.txt",
            f"The authorized archive contains {shared_terms}",
            ("Virelia ledger", "Cobalt archive"),
        )
        restricted_document = _seed_search_document(
            db,
            tenant.id,
            restricted_source.id,
            "restricted-ledger.txt",
            f"The restricted archive contains {shared_terms} "
            "with a quartz payroll marker.",
            ("Virelia ledger", "Cobalt archive"),
        )
        foreign_document = _seed_search_document(
            db,
            foreign_tenant.id,
            foreign_source.id,
            "foreign-observatory.txt",
            "Nacre observatory calibrates the heliograph array each winter.",
            ("Nacre observatory", "Heliograph array"),
        )

        embedding_provider = StubEmbeddingProvider()
        vector_search = VectorSearchService(
            db=db,
            embedding_provider=embedding_provider,
        )
        lexical_search = LexicalSearchService(db=db)
        graph_search = GraphSearchService()
        reranker = PassthroughReranker()
        searchers = {
            "vector": vector_search.search,
            "lexical": lexical_search.search,
            "hybrid": HybridSearchService(
                vector_search=vector_search,
                lexical_search=lexical_search,
                graph_search=NoGraphSearch(),
                reranker=reranker,
                rrf=ReciprocalRankFusion(),
            ).search,
            "graph_assisted_hybrid": HybridSearchService(
                vector_search=vector_search,
                lexical_search=lexical_search,
                graph_search=graph_search,
                reranker=reranker,
                rrf=ReciprocalRankFusion(),
            ).search,
        }

        def search(name: str, tenant_id, user_id, query: str) -> list[dict]:
            return searchers[name](
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                query=query,
                limit=10,
            )

        authorized_query = "Virelia cobalt ledger records"
        unauthorized_only_query = "quartz payroll marker"
        foreign_query = "Nacre observatory heliograph array"

        for method_name in searchers:
            alice_authorized = search(
                method_name, tenant.id, alice.id, authorized_query
            )
            bob_restricted_candidate = search(
                method_name, tenant.id, bob.id, authorized_query
            )
            bob_restricted_only = search(
                method_name, tenant.id, bob.id, unauthorized_only_query
            )
            alice_restricted_only = search(
                method_name, tenant.id, alice.id, unauthorized_only_query
            )
            alice_cross_tenant = search(
                method_name, tenant.id, alice.id, foreign_query
            )
            carol_foreign_candidate = search(
                method_name, foreign_tenant.id, carol.id, foreign_query
            )

            assert authorized_document.id in _document_ids(alice_authorized), method_name
            assert restricted_document.id not in _document_ids(alice_authorized), method_name
            assert restricted_document.id in _document_ids(bob_restricted_candidate), method_name
            assert restricted_document.id in _document_ids(bob_restricted_only), method_name
            assert restricted_document.id not in _document_ids(alice_restricted_only), method_name
            assert foreign_document.id not in _document_ids(alice_cross_tenant), method_name
            assert foreign_document.id in _document_ids(carol_foreign_candidate), method_name
    finally:
        db.close()
        transaction.rollback()
        connection.close()