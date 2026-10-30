from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import AuthenticatedPrincipal, get_authenticated_principal
from apps.api.config import settings
from apps.api.dependencies import get_db
from apps.api.main import app
from apps.api.services.document_service import DocumentService
from packages.domain.models import DataSource
from packages.ingestion.local_storage import LocalObjectStorage
from packages.ingestion.upload_validation import (
    UploadValidationError,
    validate_upload_content,
)


class UploadDB:
    def __init__(self, tenant_id, data_source_id):
        self.tenant_id = tenant_id
        self.data_source_id = data_source_id

    def scalar(self, statement):
        return SimpleNamespace(is_tenant_admin=True)

    def get(self, model, identity):
        if model is DataSource and identity == self.data_source_id:
            return SimpleNamespace(
                id=self.data_source_id,
                tenant_id=self.tenant_id,
            )
        return None


@pytest.mark.parametrize(
    ("content", "mime_type"),
    [
        (b"", "text/plain"),
        (b"\xff\xfe\x00", "text/plain"),
        (b"not a pdf", "application/pdf"),
        (b"binary\x00content", "text/markdown"),
    ],
)
def test_invalid_upload_content_is_rejected(content, mime_type):
    with pytest.raises(UploadValidationError):
        validate_upload_content(content, mime_type, max_pdf_pages=1000)


def test_supported_text_content_is_validated():
    validate_upload_content("hello UTF-8".encode(), "text/plain", max_pdf_pages=1000)
    validate_upload_content(b"# heading", "text/markdown", max_pdf_pages=1000)


def test_upload_size_limit_and_actual_bytes(monkeypatch):
    tenant_id = uuid4()
    data_source_id = uuid4()
    principal = AuthenticatedPrincipal(
        user_id=uuid4(),
        tenant_id=tenant_id,
        issuer="https://issuer.example",
        subject="upload-test",
        email="admin@example.com",
    )

    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    monkeypatch.setattr(settings, "max_pdf_pages", 1000)

    db = UploadDB(tenant_id, data_source_id)
    app.dependency_overrides[get_authenticated_principal] = lambda: principal
    app.dependency_overrides[get_db] = lambda: db

    document_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()
    monkeypatch.setattr(
        DocumentService,
        "create_document",
        lambda *args, **kwargs: (
            SimpleNamespace(id=document_id),
            SimpleNamespace(id=version_id),
            SimpleNamespace(id=job_id),
        ),
    )

    try:
        with TestClient(app) as client:
            at_limit = client.post(
                f"/tenants/{tenant_id}/documents?data_source_id={data_source_id}",
                files={"file": ("eight.txt", b"abcdefgh", "text/plain")},
            )
            above_limit = client.post(
                f"/tenants/{tenant_id}/documents?data_source_id={data_source_id}",
                files={"file": ("nine.txt", b"abcdefghi", "text/plain")},
            )
            misleading_length = client.post(
                f"/tenants/{tenant_id}/documents?data_source_id={data_source_id}",
                files={"file": ("nine.txt", b"abcdefghi", "text/plain")},
                headers={"content-length": "1"},
            )
            empty = client.post(
                f"/tenants/{tenant_id}/documents?data_source_id={data_source_id}",
                files={"file": ("empty.txt", b"", "text/plain")},
            )
            unsupported = client.post(
                f"/tenants/{tenant_id}/documents?data_source_id={data_source_id}",
                files={"file": ("image.bin", b"binary", "application/octet-stream")},
            )
    finally:
        app.dependency_overrides.clear()

    assert at_limit.status_code == 201
    assert above_limit.status_code == 413
    assert misleading_length.status_code == 413
    assert empty.status_code == 400
    assert unsupported.status_code == 415


def test_local_storage_keeps_version_keys_unique(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    storage.put("versions/a/source", b"version A")

    with pytest.raises(FileExistsError):
        storage.put("versions/a/source", b"overwritten content")

    assert storage.get("versions/a/source") == b"version A"
    storage.put("versions/b/source", b"version B")
    assert storage.get("versions/b/source") == b"version B"
