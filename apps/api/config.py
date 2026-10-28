from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    storage_root: Path = Path("data")

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()