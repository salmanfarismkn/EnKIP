from pathlib import Path

import pytest

from apps.api.config import settings, validate_deployment_configuration


def test_production_rejects_development_auth(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "development")
    monkeypatch.setattr(settings, "storage_root", Path("/var/lib/enkip/source"))

    with pytest.raises(RuntimeError, match="Development authentication"):
        validate_deployment_configuration()


def test_production_rejects_ephemeral_storage(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "storage_root", Path("data"))

    with pytest.raises(RuntimeError, match="persistent deployment path"):
        validate_deployment_configuration()
