from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SKILLFORGE_", extra="ignore")

    postgres_dsn: str = "postgresql://skillforge:skillforge@localhost:5432/skillforge"
    qdrant_url: str = "http://localhost:6333"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(min_length=8, default="skillforge-dev")
    dense_model: str = "intfloat/multilingual-e5-large"
    sparse_model: str = "Qdrant/bm25"
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=60)
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    notebook_timeout_seconds: int = Field(default=30, ge=1, le=120)
    llm_enabled: bool = False

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.llm_enabled
            and self.llm_base_url
            and self.llm_model
            and self.llm_api_key is not None
            and self.llm_api_key.get_secret_value().strip()
        )
