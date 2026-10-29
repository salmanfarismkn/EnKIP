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


settings = Settings()