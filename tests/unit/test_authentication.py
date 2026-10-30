from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from apps.api import auth
from apps.api.main import app
from apps.api.config import settings
from packages.domain.models import User


@pytest.fixture
def rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


class FakeJWKClient:
    def __init__(self, public_key, kid="test-key"):
        self.public_key = public_key
        self.kid = kid

    def get_signing_key_from_jwt(self, token):
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise exc
        if header.get("kid") != self.kid:
            raise jwt.PyJWKClientError("unknown key")
        return SimpleNamespace(key=self.public_key)


def encode_token(private_key, *, issuer=None, audience=None, expires=None, nbf=None, kid="test-key", subject="external-subject"):
    now = datetime.now(timezone.utc)
    issuer = issuer or settings.oidc_issuer
    audience = audience or settings.oidc_audience
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": expires or now + timedelta(minutes=5),
        "nbf": nbf or now - timedelta(seconds=1),
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(autouse=True)
def oidc_settings(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", "https://issuer.example")
    monkeypatch.setattr(settings, "oidc_audience", "enkip-api")
    monkeypatch.setattr(settings, "oidc_jwks_uri", "https://issuer.example/.well-known/jwks.json")
    monkeypatch.setattr(settings, "oidc_algorithms", "RS256")
    monkeypatch.setattr(settings, "oidc_required_claims", "")
    monkeypatch.setattr(settings, "oidc_jwks_cache_ttl_seconds", 300)


def test_valid_token_verifies_and_resolves_user(rsa_keys, monkeypatch):
    private_key, public_key = rsa_keys
    monkeypatch.setattr(auth, "_get_jwk_client", lambda: FakeJWKClient(public_key))
    token = encode_token(private_key)

    claims = auth._verify_oidc_token(token)
    assert claims["sub"] == "external-subject"

    user = User(id=uuid4(), tenant_id=uuid4(), email="user@example.com", display_name="User", enabled=True)
    db = SimpleNamespace(scalar=lambda statement: user)
    principal = auth._resolve_external_identity(db, claims)
    assert principal.user_id == user.id
    assert principal.tenant_id == user.tenant_id


def test_missing_and_malformed_tokens(monkeypatch):
    with pytest.raises(HTTPException) as missing:
        auth.get_authenticated_principal(credentials=None, db=object())
    assert missing.value.status_code == 401

    monkeypatch.setattr(auth, "_get_jwk_client", lambda: FakeJWKClient(rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()))
    with pytest.raises(HTTPException) as malformed:
        auth._verify_oidc_token("not-a-jwt")
    assert malformed.value.status_code == 401


def test_invalid_signature_expiry_issuer_audience_are_rejected(rsa_keys, monkeypatch):
    private_key, public_key = rsa_keys
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(auth, "_get_jwk_client", lambda: FakeJWKClient(public_key))

    bad_signature = encode_token(other_key)
    expired = encode_token(private_key, expires=datetime.now(timezone.utc) - timedelta(seconds=1))
    wrong_issuer = encode_token(private_key, issuer="https://wrong.example")
    wrong_audience = encode_token(private_key, audience="another-api")

    for token in (bad_signature, expired, wrong_issuer, wrong_audience):
        with pytest.raises(HTTPException) as exc:
            auth._verify_oidc_token(token)
        assert exc.value.status_code == 401


def test_unknown_key_id_and_rotation(rsa_keys, monkeypatch):
    private_key, public_key = rsa_keys
    monkeypatch.setattr(auth, "_get_jwk_client", lambda: FakeJWKClient(public_key, kid="new-key"))

    old_key_token = encode_token(private_key, kid="old-key")
    with pytest.raises(HTTPException) as old_key:
        auth._verify_oidc_token(old_key_token)
    assert old_key.value.status_code == 401

    rotated_token = encode_token(private_key, kid="new-key")
    assert auth._verify_oidc_token(rotated_token)["sub"] == "external-subject"


def test_unknown_disabled_and_non_member_identity(monkeypatch):
    claims = {"iss": "https://issuer.example", "sub": "unknown-subject"}
    with pytest.raises(HTTPException) as unknown:
        auth._resolve_external_identity(SimpleNamespace(scalar=lambda statement: None), claims)
    assert unknown.value.status_code == 401

    with pytest.raises(HTTPException) as disabled:
        auth._resolve_external_identity(SimpleNamespace(scalar=lambda statement: None), claims)
    assert disabled.value.status_code == 401

    principal = auth.AuthenticatedPrincipal(uuid4(), uuid4(), "issuer", "subject", "user@example.com")
    with pytest.raises(HTTPException) as non_member:
        auth.require_tenant_membership(uuid4(), principal)
    assert non_member.value.status_code == 403


def test_production_startup_rejects_missing_oidc_settings(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", None)
    monkeypatch.setattr(settings, "oidc_audience", None)
    monkeypatch.setattr(settings, "oidc_jwks_uri", None)

    with pytest.raises(RuntimeError, match="OIDC issuer"):
        auth.validate_auth_configuration()


def test_production_startup_rejects_invalid_oidc_urls(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", "http://issuer.example")
    monkeypatch.setattr(settings, "oidc_audience", "enkip-api")
    monkeypatch.setattr(settings, "oidc_jwks_uri", "https://issuer.example/jwks")

    with pytest.raises(RuntimeError, match="must use HTTPS"):
        auth.validate_auth_configuration()

    monkeypatch.setattr(settings, "oidc_issuer", "https://issuer.example")
    monkeypatch.setattr(settings, "oidc_jwks_uri", "not-a-url")
    with pytest.raises(RuntimeError, match="absolute HTTP"):
        auth.validate_auth_configuration()


def test_development_bypass_is_disabled_by_default_and_rejected_in_production(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "development")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "development_user_id", None)
    with pytest.raises(RuntimeError, match="ENKIP_DEV_USER_ID"):
        auth.validate_auth_configuration()

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "development_user_id", str(uuid4()))
    with pytest.raises(RuntimeError, match="cannot be enabled in production"):
        auth.validate_auth_configuration()


def test_token_errors_and_principal_errors_do_not_echo_token(rsa_keys, monkeypatch):
    private_key, public_key = rsa_keys
    token = encode_token(private_key)
    monkeypatch.setattr(auth, "_get_jwk_client", lambda: FakeJWKClient(public_key))
    claims = auth._verify_oidc_token(token)

    with pytest.raises(HTTPException) as exc:
        auth._resolve_external_identity(SimpleNamespace(scalar=lambda statement: None), claims)
    assert token not in str(exc.value.detail)
    assert "External identity" in str(exc.value.detail)


def test_tenant_admin_role_is_checked_from_live_database_record():
    tenant_id = uuid4()
    principal = auth.AuthenticatedPrincipal(uuid4(), tenant_id, "issuer", "subject", "user@example.com")

    member = SimpleNamespace(is_tenant_admin=False)
    with pytest.raises(HTTPException) as exc:
        auth.require_tenant_admin(tenant_id, principal, SimpleNamespace(scalar=lambda statement: member))
    assert exc.value.status_code == 403

    admin = SimpleNamespace(is_tenant_admin=True)
    auth.require_tenant_admin(tenant_id, principal, SimpleNamespace(scalar=lambda statement: admin))


def test_tenant_spoofing_is_rejected():
    tenant_id = uuid4()
    principal_tenant_id = uuid4()
    principal = auth.AuthenticatedPrincipal(uuid4(), principal_tenant_id, "issuer", "subject", "user@example.com")
    with pytest.raises(HTTPException) as exc:
        auth.require_tenant_membership(tenant_id, principal)
    assert exc.value.status_code == 403


def test_protected_route_returns_401_for_missing_token_and_ignores_user_spoof():
    tenant_id = uuid4()
    with TestClient(app) as client:
        response = client.post(
            f"/tenants/{tenant_id}/search?user_id={uuid4()}",
            json={"query": "test", "limit": 10},
        )
    assert response.status_code == 401
    assert "Bearer" in response.headers["www-authenticate"]
    assert "user_id" not in response.text
