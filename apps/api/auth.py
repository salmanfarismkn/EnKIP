from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import settings
from apps.api.dependencies import get_db
from packages.domain.models import ExternalIdentity, User


_bearer = HTTPBearer(auto_error=False)
_jwk_clients: dict[tuple[str, int, int], PyJWKClient] = {}


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: UUID
    tenant_id: UUID
    issuer: str
    subject: str
    email: str


def validate_auth_configuration() -> None:
    app_env = settings.app_env.strip().lower()
    auth_mode = settings.auth_mode.strip().lower()

    if auth_mode == "development":
        if app_env == "production":
            raise RuntimeError("Development authentication bypass cannot be enabled in production")
        if not settings.development_user_id:
            raise RuntimeError("ENKIP_DEV_USER_ID is required for development authentication")
        return

    if auth_mode != "oidc":
        raise RuntimeError("AUTH_MODE must be 'oidc' or 'development'")

    issuer = settings.oidc_issuer.strip() if settings.oidc_issuer else ""
    audience = settings.oidc_audience.strip() if settings.oidc_audience else ""
    jwks_uri = settings.oidc_jwks_uri.strip() if settings.oidc_jwks_uri else ""

    if app_env == "production" and not (issuer and audience and jwks_uri):
        raise RuntimeError("OIDC issuer, audience, and JWKS URI must be configured in production")

    issuer_url = urlparse(issuer) if issuer else None
    jwks_url = urlparse(jwks_uri) if jwks_uri else None
    if issuer_url and (issuer_url.scheme not in ("https", "http") or not issuer_url.netloc):
        raise RuntimeError("OIDC_ISSUER must be an absolute HTTP(S) issuer URL")
    if jwks_url and (jwks_url.scheme not in ("https", "http") or not jwks_url.netloc):
        raise RuntimeError("OIDC_JWKS_URI must be an absolute HTTP(S) JWKS URL")
    if app_env == "production" and issuer and issuer_url and issuer_url.scheme != "https":
        raise RuntimeError("OIDC_ISSUER must use HTTPS in production")
    if app_env == "production" and jwks_uri and jwks_url and jwks_url.scheme != "https":
        raise RuntimeError("OIDC_JWKS_URI must use HTTPS in production")

    algorithms = allowed_algorithms()
    if not algorithms:
        raise RuntimeError("OIDC_ALGORITHMS must contain at least one algorithm")
    if settings.oidc_jwks_cache_ttl_seconds < 30:
        raise RuntimeError("OIDC_JWKS_CACHE_TTL_SECONDS must be at least 30")


def allowed_algorithms() -> tuple[str, ...]:
    algorithms = tuple(
        value.strip()
        for value in settings.oidc_algorithms.split(",")
        if value.strip()
    )
    allowed_asymmetric = {
        "RS256", "RS384", "RS512",
        "ES256", "ES384", "ES512",
        "PS256", "PS384", "PS512",
        "EdDSA",
    }
    return tuple(value for value in algorithms if value in allowed_asymmetric)


def _get_jwk_client() -> PyJWKClient:
    jwks_uri = settings.oidc_jwks_uri.strip() if settings.oidc_jwks_uri else ""
    if not jwks_uri:
        raise HTTPException(status_code=503, detail="Authentication service is not configured")

    key = (
        jwks_uri,
        settings.oidc_jwks_cache_ttl_seconds,
        16,
    )
    client = _jwk_clients.get(key)
    if client is None:
        client = PyJWKClient(
            jwks_uri,
            cache_keys=True,
            lifespan=settings.oidc_jwks_cache_ttl_seconds,
            max_cached_keys=16,
        )
        _jwk_clients[key] = client
    return client


def _unauthorized(detail: str = "Invalid or missing authentication credential") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _verify_oidc_token(token: str) -> dict:
    try:
        issuer = settings.oidc_issuer.strip() if settings.oidc_issuer else ""
        audience = settings.oidc_audience.strip() if settings.oidc_audience else ""
        if not issuer or not audience:
            raise _unauthorized("Authentication service is not configured")
        algorithms = allowed_algorithms()
        if not algorithms:
            raise _unauthorized("Authentication algorithm configuration is invalid")

        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        required = {"sub", "exp", "nbf", "iss", "aud"}
        for claim in (
            value.strip()
            for value in settings.oidc_required_claims.split(",")
            if value.strip()
        ):
            required.add(claim)

        return jwt.decode(
            token,
            signing_key.key,
            algorithms=list(algorithms),
            issuer=issuer,
            audience=audience,
            options={"require": sorted(required)},
        )
    except HTTPException:
        raise
    except jwt.PyJWTError:
        raise _unauthorized()


def _resolve_external_identity(db: Session, claims: dict) -> AuthenticatedPrincipal:
    issuer = claims["iss"]
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject.strip():
        raise _unauthorized()

    user = db.scalar(
        select(User)
        .join(ExternalIdentity, ExternalIdentity.user_id == User.id)
        .where(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
            User.enabled.is_(True),
        )
    )
    if user is None:
        raise _unauthorized("External identity is not linked to an enabled user")

    return AuthenticatedPrincipal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        issuer=issuer,
        subject=subject,
        email=user.email,
    )


def get_authenticated_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    auth_mode = settings.auth_mode.strip().lower()

    if auth_mode == "development":
        if settings.app_env.strip().lower() == "production":
            raise _unauthorized()
        if not settings.development_user_id:
            raise _unauthorized()
        try:
            user_id = UUID(settings.development_user_id)
        except ValueError:
            raise _unauthorized()
        user = db.get(User, user_id)
        if user is None or not user.enabled:
            raise _unauthorized()
        return AuthenticatedPrincipal(
            user_id=user.id,
            tenant_id=user.tenant_id,
            issuer="development",
            subject=str(user.id),
            email=user.email,
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    claims = _verify_oidc_token(credentials.credentials)
    return _resolve_external_identity(db, claims)


def require_tenant_membership(
    tenant_id: UUID,
    principal: AuthenticatedPrincipal,
) -> None:
    if tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The authenticated user is not a member of this tenant",
        )


def require_tenant_admin(
    tenant_id: UUID,
    principal: AuthenticatedPrincipal,
    db: Session,
) -> None:
    require_tenant_membership(tenant_id, principal)
    user = db.scalar(
        select(User).where(
            User.id == principal.user_id,
            User.tenant_id == tenant_id,
            User.enabled.is_(True),
        )
    )
    if user is None or not user.is_tenant_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrator access is required",
        )
