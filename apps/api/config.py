from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    storage_root: Path = Path("data")
    max_upload_bytes: int = 25 * 1024 * 1024
    max_ingestion_source_bytes: int = 25 * 1024 * 1024
    max_ingestion_chunks: int = 10_000
    max_pdf_pages: int = 1_000

    embedding_model: str
    embedding_dimensions: int

    generation_model: str

    query_decomposition_enabled: bool = True
    decomposition_model: str

    ollama_base_url: str = "http://localhost:11434"

    app_env: str = "development"
    auth_mode: str = "oidc"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_uri: str | None = None
    oidc_algorithms: str = "RS256"
    oidc_jwks_cache_ttl_seconds: int = 300
    oidc_required_claims: str = ""
    development_user_id: str | None = None
    cors_allowed_origins: str = ""

    @field_validator(
        "max_upload_bytes",
        "max_ingestion_source_bytes",
        "max_ingestion_chunks",
        "max_pdf_pages",
    )
    @classmethod
    def positive_resource_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("resource limits must be positive")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


def validate_deployment_configuration() -> None:
    app_env = settings.app_env.strip().lower()
    if app_env == "production":
        if not settings.database_url.strip():
            raise RuntimeError("DATABASE_URL is required in production")
        if settings.auth_mode.strip().lower() == "development":
            raise RuntimeError("Development authentication cannot be enabled in production")
        if not settings.embedding_model.strip():
            raise RuntimeError("EMBEDDING_MODEL is required")
        if not settings.generation_model.strip():
            raise RuntimeError("GENERATION_MODEL is required")
        if not settings.decomposition_model.strip():
            raise RuntimeError("DECOMPOSITION_MODEL is required")
        if settings.embedding_dimensions <= 0:
            raise RuntimeError("EMBEDDING_DIMENSIONS must be positive")
        if settings.storage_root == Path("data"):
            raise RuntimeError("STORAGE_ROOT must be a persistent deployment path in production")


settings = Settings()