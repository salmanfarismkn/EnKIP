import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import URLError
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.api.main import create_app
from packages.domain.database import SessionLocal
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
from packages.retrieval.graph_search import GraphSearchService
from packages.retrieval.hybrid_search import HybridSearchService
from packages.retrieval.lexical_search import LexicalSearchService
from packages.retrieval.rrf import ReciprocalRankFusion
from packages.retrieval.vector_search import VectorSearchService
from packages.retrieval.reranker import Reranker
from packages.retrieval.local_reranker import LocalCrossEncoderReranker


pytestmark = pytest.mark.skipif(
    os.environ.get("ENKIP_RUN_BENCHMARKS") != "1",
    reason="performance benchmarks are opt-in with ENKIP_RUN_BENCHMARKS=1",
)


class SyntheticEmbedding:
    def __init__(self, vector, dimensions=1024):
        self.vector = vector

    @property
    def model_name(self):
        return "benchmark-synthetic-1024"

    @property
    def model_version(self):
        return "v1"

    @property
    def dimensions(self):
        return 1024

    def embed(self, query):
        del query
        return SyntheticEmbedding([0.25] * 1024)


class IdentityReranker(Reranker):
    def rerank(self, query, results):
        del query
        return results


def _latency(values):
    ordered = sorted(values)
    if not ordered:
        return {"p50_ms": None, "p95_ms": None, "p99_ms": None}

    def percentile(sample, ratio):
        index = max(0, min(len(sample) - 1, round((len(sample) - 1) * ratio)))
        return sample[index] * 1000.0

    return {
        "p50_ms": round(percentile(ordered, 0.50), 3),
        "p95_ms": round(percentile(ordered, 0.95), 3),
        "p99_ms": round(percentile(ordered, 0.99), 3),
        "mean_ms": round(statistics.fmean(ordered) * 1000.0, 3),
    }


def _run(name, operation, requests=100, concurrency=1):
    latencies = []
    errors = 0
    started = time.perf_counter()

    def invoke(_):
        sample_started = time.perf_counter()
        try:
            operation()
            return time.perf_counter() - sample_started, None
        except Exception as exc:
            return time.perf_counter() - sample_started, type(exc).__name__

    if concurrency == 1:
        samples = [invoke(i) for i in range(requests)]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            samples = list(executor.map(invoke, range(requests)))

    for latency, error in samples:
        latencies.append(latency)
        if error is not None:
            errors += 1

    elapsed = time.perf_counter() - started
    return {
        "benchmark": name,
        "requests": requests,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_rps": round(requests / elapsed, 3),
        "error_count": errors,
        "error_rate": round(errors / requests, 6),
        **_latency(latencies),
    }


def _run_vector_session(tenant_id, user_id):
    provider = SyntheticEmbedding([0.25] * 1024)
    with SessionLocal() as db:
        service = VectorSearchService(db, provider)
        service.search(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            query="authorization benchmark",
            limit=10,
        )


def _seed(db, document_count=100, chunks_per_document=10):
    started = time.perf_counter()
    tenant = Tenant(name=f"benchmark-{uuid4()}")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"benchmark-{uuid4()}@example.invalid",
        display_name="Benchmark User",
        enabled=True,
        is_tenant_admin=False,
    )
    source = DataSource(
        tenant_id=tenant.id,
        name="Synthetic Benchmark Source",
        source_type="benchmark",
    )
    db.add_all([user, source])
    db.flush()
    db.add(DataSourceAccess(
        tenant_id=tenant.id,
        user_id=user.id,
        data_source_id=source.id,
    ))

    vector = [0.25] * 1024
    entities = {}
    for topic_index in range(20):
        entity = Entity(
            tenant_id=tenant.id,
            canonical_name=f"Topic {topic_index}",
            entity_type="benchmark_topic",
        )
        db.add(entity)
        db.flush()
        entities[topic_index] = entity

    for document_index in range(document_count):
        document = Document(
            tenant_id=tenant.id,
            data_source_id=source.id,
            title=f"Synthetic document {document_index}",
            mime_type="text/plain",
            object_key=f"benchmark/{document_index}/version-1.txt",
        )
        db.add(document)
        db.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            checksum=f"{document_index:064x}",
            source_object_key=f"benchmark/{document_index}/version-1.txt",
            source_mime_type="text/plain",
            processing_status="completed",
        )
        db.add(version)
        db.flush()
        entity = entities[document_index % 20]
        for chunk_index in range(chunks_per_document):
            chunk = DocumentChunk(
                tenant_id=tenant.id,
                document_version_id=version.id,
                chunk_index=chunk_index,
                section_title="Synthetic Section",
                text=(
                    f"Synthetic benchmark document {document_index} chunk {chunk_index}. "
                    "PostgreSQL authorization lexical graph hybrid vector retrieval benchmark."
                ),
                page_number=chunk_index + 1,
            )
            db.add(chunk)
            db.flush()
            db.add(ChunkEmbedding(
                tenant_id=tenant.id,
                chunk_id=chunk.id,
                model_name="benchmark-synthetic-1024",
                model_version="v1",
                dimensions=1024,
                embedding=vector,
            ))
            db.add(EntityRelationship(
                tenant_id=tenant.id,
                source_entity_id=entity.id,
                target_entity_id=entity.id,
                relationship_type="synthetic_related_to",
                source_chunk_id=chunk.id,
                confidence=1.0,
            ))
    db.commit()
    return tenant, user, time.perf_counter() - started


@pytest.mark.skipif(
    os.environ.get("ENKIP_RUN_BENCHMARKS") != "1",
    reason="performance benchmarks are opt-in with ENKIP_RUN_BENCHMARKS=1",
)
def test_capacity_benchmark(capsys):
    results = {
        "synthetic": True,
        "dataset": {"documents": 100, "chunks_per_document": 10, "chunks": 1000},
        "warmup_requests": 5,
        "concurrency": 8,
        "request_counts": {"warm": 100, "api": 200},
    }
    with SessionLocal() as db:
        tenant, user, seed_seconds = _seed(db)
        results["synthetic_seed_seconds"] = round(seed_seconds, 3)
        results["synthetic_ingestion_persistence_chunks_per_second"] = round(
            1000 / seed_seconds,
            3,
        )
        vector = VectorSearchService(db, SyntheticEmbedding([0.25] * 1024))
        lexical = LexicalSearchService(db)
        graph = GraphSearchService()
        hybrid = HybridSearchService(
            vector_search=vector,
            lexical_search=lexical,
            graph_search=graph,
            reranker=IdentityReranker(),
            rrf=ReciprocalRankFusion(),
        )

        vector_op = lambda: vector.search(
            db=db, tenant_id=tenant.id, user_id=user.id,
            query="authorization benchmark", limit=10,
        )
        lexical_op = lambda: lexical.search(
            db=db, tenant_id=tenant.id, user_id=user.id,
            query="authorization benchmark", limit=10,
        )
        graph_op = lambda: graph.search(
            db=db, tenant_id=tenant.id, user_id=user.id,
            query="Topic 1", limit=10,
        )
        hybrid_op = lambda: hybrid.search(
            db=db, tenant_id=tenant.id, user_id=user.id,
            query="authorization benchmark", limit=10,
        )
        for operation in (vector_op, lexical_op, graph_op, hybrid_op):
            for _ in range(5):
                operation()

        results["retrieval"] = [
            _run("vector_search", vector_op, requests=100, concurrency=1),
            _run("lexical_search", lexical_op, requests=100, concurrency=1),
            _run("graph_assisted_search", graph_op, requests=100, concurrency=1),
            _run("hybrid_search_with_identity_reranker", hybrid_op, requests=100, concurrency=1),
            _run(
                "vector_search_concurrent",
                lambda: _run_vector_session(tenant.id, user.id),
                requests=200,
                concurrency=8,
            ),
        ]

        explain_vector = db.execute(text(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
            "SELECT dc.id FROM document_chunks dc "
            "JOIN document_versions dv ON dv.id=dc.document_version_id "
            "JOIN documents d ON d.id=dv.document_id "
            "JOIN chunk_embeddings ce ON ce.chunk_id=dc.id "
            "WHERE dc.tenant_id=:tenant_id AND ce.tenant_id=:tenant_id "
            "ORDER BY ce.embedding <=> ce.embedding "
            "LIMIT 10"
        ), {"tenant_id": tenant.id}).scalars().all()
        explain_lexical = db.execute(text(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) "
            "SELECT dc.id FROM document_chunks dc "
            "WHERE dc.tenant_id=:tenant_id "
            "AND dc.search_vector @@ websearch_to_tsquery('english', 'authorization benchmark') "
            "ORDER BY ts_rank_cd(dc.search_vector, websearch_to_tsquery('english', 'authorization benchmark')) DESC "
            "LIMIT 10"
        ), {"tenant_id": tenant.id}).scalars().all()
        results["query_plans"] = {
            "vector": explain_vector,
            "lexical": explain_lexical,
        }
        max_connections = db.scalar(text("SHOW max_connections"))
        results["database"] = {
            "postgresql": db.scalar(text("SHOW server_version")),
            "pgvector": db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'")),
            "max_connections": int(max_connections),
            "sqlalchemy_pool_size": 5,
            "sqlalchemy_pool_overflow": 10,
        }

    app = create_app()
    with TestClient(app) as client:
        client.get("/live")
        client.get("/ready")
        results["api"] = [
            _run(
                "liveness",
                lambda: client.get("/live"),
                requests=200,
                concurrency=8,
            ),
            _run(
                "readiness",
                lambda: client.get("/ready"),
                requests=200,
                concurrency=8,
            ),
        ]

    results["ollama"] = {}
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            results["ollama"]["reachable"] = True
            results["ollama"]["models"] = [
                model.get("name")
                for model in payload.get("models", [])
            ]
        embed_request = Request(
            "http://127.0.0.1:11434/api/embed",
            data=json.dumps({
                "model": "qwen3-embedding:0.6b",
                "input": "Synthetic authorization benchmark query",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        embed_started = time.perf_counter()
        with urlopen(embed_request, timeout=120) as response:
            embed_payload = json.loads(response.read().decode("utf-8"))
        results["ollama"]["embedding_model"] = "qwen3-embedding:0.6b"
        results["ollama"]["embedding_latency_ms"] = round(
            (time.perf_counter() - embed_started) * 1000.0,
            3,
        )
        results["ollama"]["embedding_dimensions"] = len(
            embed_payload.get("embeddings", [[]])[0]
        )
    except (URLError, TimeoutError, OSError) as exc:
        results["ollama"]["reachable"] = False
        results["ollama"]["error_category"] = type(exc).__name__

    try:
        reranker = LocalCrossEncoderReranker()
        candidates = [
            {
                "chunk_id": str(index),
                "text": (
                    "Synthetic benchmark passage about authorization and retrieval "
                    f"candidate {index}"
                ),
            }
            for index in range(10)
        ]
        reranker.rerank(
            "authorization retrieval",
            candidates,
        )
        rerank_started = time.perf_counter()
        reranker.rerank(
            "authorization retrieval",
            candidates,
        )
        results["reranker"] = {
            "model": reranker.model_name,
            "candidates": 10,
            "latency_ms": round(
                (time.perf_counter() - rerank_started) * 1000.0,
                3,
            ),
        }
    except Exception as exc:
        results["reranker"] = {
            "verified": False,
            "error_category": type(exc).__name__,
        }

    print(json.dumps(results, indent=2, sort_keys=True))
