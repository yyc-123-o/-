from pydantic import Field
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
