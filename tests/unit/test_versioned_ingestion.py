from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.api.services.document_service import _version_source_key
from apps.worker.services import ingestion_service as ingestion_module
from apps.worker.services.ingestion_service import IngestionService
from packages.domain.models import (
    DocumentProcessingStatus,
    IngestionStatus,
)
from packages.ingestion.local_storage import LocalObjectStorage
from packages.retrieval.graph_extraction import GraphExtractionResult
from packages.ingestion.models import ParsedDocument, ParsedSection


class MemoryStorage:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.read_keys: list[str] = []

    def get(self, key: str) -> bytes:
        self.read_keys.append(key)
        return self.objects[key]


class FakeDatabase:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class FakeChunkService:
    def __init__(self) -> None:
        self.chunk_texts: list[str] = []

    def replace_chunks(self, tenant_id, document_version_id, chunks):
        self.chunk_texts = [chunk.text for chunk in chunks]
        return [
            SimpleNamespace(id=uuid4(), text=chunk.text)
            for chunk in chunks
        ]


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.chunk_texts: list[str] = []

    def embed_chunks(self, tenant_id, chunks) -> None:
        self.chunk_texts = [chunk.text for chunk in chunks]


def _service(storage: MemoryStorage) -> IngestionService:
    return IngestionService(
        db=None,
        storage=storage,
        parser_registry=None,
        chunker=None,
        chunk_service=None,
        embedding_service=None,
    )


def test_worker_processes_queued_version_not_current_document_pointer(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    key_a = _version_source_key(tenant_id, document_id, version_id)
    key_b = _version_source_key(tenant_id, document_id, uuid4())
    content_a = b"version A source"
    content_b = b"version B source"
    version, job = _version_and_job(key_a, content_a)
    version.document_id = document_id
    version.source_mime_type = "text/plain"
    version.processing_status = DocumentProcessingStatus.PENDING
    version.processing_error = None
    version.extracted_text = None
    job.id = uuid4()
    job.status = IngestionStatus.PENDING
    job.attempt_count = 1
    job.max_attempts = 3
    job.started_at = None
    job.completed_at = None
    job.error_message = None
    job.last_error = None
    job.claimed_at = None
    document = SimpleNamespace(
        id=document_id,
        tenant_id=tenant_id,
        title="source.txt",
        mime_type="application/pdf",
        object_key=key_b,
    )
    storage = MemoryStorage({key_a: content_a, key_b: content_b})
    parser_inputs: list[bytes] = []
    parser_mime_types: list[str] = []

    class TrackingParser:
        def parse(self, content: bytes, filename: str) -> ParsedDocument:
            parser_inputs.append(content)
            return ParsedDocument(
                title=filename,
                mime_type="text/plain",
                sections=[ParsedSection(title=None, text=content.decode())],
            )

    class TrackingParserRegistry:
        def get_parser(self, mime_type: str) -> TrackingParser:
            parser_mime_types.append(mime_type)
            return TrackingParser()

    class EmptyGraphExtractor:
        def __init__(self, **kwargs) -> None:
            pass

        def extract(self, text: str) -> GraphExtractionResult:
            return GraphExtractionResult(entities=[], relationships=[])

    class NoopGraphService:
        def persist_extraction(self, **kwargs) -> None:
            pass

    chunks = FakeChunkService()
    embeddings = FakeEmbeddingService()
    service = IngestionService(
        db=FakeDatabase(),
        storage=storage,
        parser_registry=TrackingParserRegistry(),
        chunker=ingestion_module.DocumentChunker(),
        chunk_service=chunks,
        embedding_service=embeddings,
    )
    service._get_job = lambda job_id: job
    service._get_version = lambda document_version_id: version
    service._get_document = lambda found_document_id: document
    monkeypatch.setattr(
        ingestion_module,
        "OllamaGraphExtractor",
        EmptyGraphExtractor,
    )
    monkeypatch.setattr(
        ingestion_module,
        "GraphService",
        NoopGraphService,
    )

    service.process_job(job.id)

    assert storage.read_keys == [key_a]
    assert parser_inputs == [content_a]
    assert parser_mime_types == ["text/plain"]
    assert chunks.chunk_texts == [content_a.decode()]
    assert embeddings.chunk_texts == [content_a.decode()]
    assert version.extracted_text == content_a.decode()
    assert version.processing_status == DocumentProcessingStatus.COMPLETED
    assert job.status == IngestionStatus.COMPLETED


def _version_and_job(
    source_key: str,
    content: bytes,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    version_id = uuid4()
    checksum = sha256(content).hexdigest()
    version = SimpleNamespace(
        id=version_id,
        source_object_key=source_key,
        checksum=checksum,
    )
    job = SimpleNamespace(
        document_version_id=version_id,
        expected_checksum=checksum,
    )
    return version, job


def test_worker_reads_the_queued_versions_object_after_a_new_upload() -> None:
    tenant_id = uuid4()
    document_id = uuid4()
    version_a_id = uuid4()
    version_b_id = uuid4()
    key_a = _version_source_key(tenant_id, document_id, version_a_id)
    key_b = _version_source_key(tenant_id, document_id, version_b_id)
    content_a = b"version A source"
    content_b = b"version B source"
    version_a, job_a = _version_and_job(key_a, content_a)
    storage = MemoryStorage({key_a: content_a, key_b: content_b})

    # The current document pointer can advance, but the job carries version A.
    current_document = SimpleNamespace(object_key=key_b)
    assert current_document.object_key == key_b

    service = _service(storage)

    assert service._load_verified_source(job_a, version_a) == content_a
    assert storage.read_keys == [key_a]
    assert sha256(content_a).hexdigest() == job_a.expected_checksum


def test_worker_rejects_modified_source_before_returning_content() -> None:
    source_key = "tenant/document/version/source"
    original = b"original source"
    modified = b"changed source!"
    version, job = _version_and_job(source_key, original)
    storage = MemoryStorage({source_key: modified})

    with pytest.raises(ValueError, match="checksum mismatch"):
        _service(storage)._load_verified_source(job, version)

    assert storage.read_keys == [source_key]


def test_worker_retries_read_the_same_version_object() -> None:
    source_key = "tenant/document/version-a/source"
    content = b"version A source"
    version, job = _version_and_job(source_key, content)
    storage = MemoryStorage({source_key: content})
    service = _service(storage)

    assert service._load_verified_source(job, version) == content
    assert service._load_verified_source(job, version) == content
    assert storage.read_keys == [source_key, source_key]


def test_job_checksum_must_match_its_version() -> None:
    source_key = "tenant/document/version/source"
    version, job = _version_and_job(source_key, b"source")
    job.expected_checksum = "0" * 64
    storage = MemoryStorage({source_key: b"source"})

    with pytest.raises(ValueError, match="does not match document version"):
        _service(storage)._load_verified_source(job, version)

    assert storage.read_keys == []


def test_job_must_reference_the_version_being_loaded() -> None:
    source_key = "tenant/document/version/source"
    version, job = _version_and_job(source_key, b"source")
    job.document_version_id = uuid4()
    storage = MemoryStorage({source_key: b"source"})

    with pytest.raises(ValueError, match="different document version"):
        _service(storage)._load_verified_source(job, version)

    assert storage.read_keys == []


def test_missing_legacy_source_key_fails_safely() -> None:
    version, job = _version_and_job("", b"source")
    version.source_object_key = None
    storage = MemoryStorage({})

    with pytest.raises(ValueError, match="no source object"):
        _service(storage)._load_verified_source(job, version)

    assert storage.read_keys == []


def test_concurrent_version_ids_produce_distinct_source_paths(
    tmp_path,
) -> None:
    tenant_id = uuid4()
    document_id = uuid4()
    version_ids = [uuid4() for _ in range(100)]
    contents = {
        version_id: f"version {index}".encode()
        for index, version_id in enumerate(version_ids)
    }

    def write_version(version_id) -> tuple[str, bytes]:
        key = _version_source_key(tenant_id, document_id, version_id)
        content = contents[version_id]
        storage.put(key, content)
        return key, content

    storage = LocalObjectStorage(tmp_path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(write_version, version_ids))

    keys = [key for key, _ in results]
    assert len(keys) == len(set(keys)) == len(version_ids)
    assert all(
        storage.get(key) == contents[version_id]
        for key, version_id in zip(keys, version_ids)
    )


def test_local_storage_does_not_overwrite_an_existing_object(
    tmp_path,
) -> None:
    storage = LocalObjectStorage(tmp_path)
    key = "tenant/document/version/source"
    storage.put(key, b"version A")

    with pytest.raises(FileExistsError):
        storage.put(key, b"version B")

    assert storage.get(key) == b"version A"
