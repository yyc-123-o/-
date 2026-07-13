# AI Learning Knowledge Base v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible bilingual AI-learning knowledge base that exposes a traceable Evidence API backed by governed sources, a concept graph, hybrid retrieval, and offline evaluation.

**Architecture:** A deterministic Python ingestion pipeline registers public sources, parses and semantically chunks content, maps chunks to a shared bilingual ontology, then publishes metadata to PostgreSQL, dense/sparse vectors to Qdrant, and relationships to Neo4j. LangChain supplies document and retriever primitives; FastAPI exposes a versioned Evidence API. LangGraph is not used in offline ingestion and will consume the API in a separate agent implementation plan.

**Tech Stack:** Python 3.12, uv, Pydantic 2, LangChain, FastAPI, PostgreSQL 16, Qdrant, Neo4j 5, PyMuPDF, Trafilatura, FastEmbed, pytest, Ruff, mypy, Docker Compose.

## Global Constraints

- Work only on the knowledge-base v1 scope; do not implement agent decision logic in this plan.
- Teaching scope is machine learning through large language models; agent development is excluded from teaching content.
- Deep modules are logistic regression, Transformer, and large language models with PEFT and RAG practice.
- Treat Chinese and English as equally important by concept-level evidence coverage, not by equal raw chunk counts.
- Publish only sources with recorded provenance, license/use status, version, and resolvable citation location.
- Every published chunk must pass automated validation and human review.
- Target 120–180 concepts, 800–1,200 total reviewed chunks, 60–90 examples/exercises, and at least 150 labeled retrieval queries.
- Acceptance thresholds: Recall@5 >= 0.85, MRR@10 >= 0.75, nDCG@10 >= 0.80, concept coverage >= 90%, Chinese/English recall gap <= 0.05, citation relocalization >= 98%, duplicate rate < 2%, local P95 retrieval latency < 2 seconds.
- Use the versioned `Evidence API`; future agents must not access PostgreSQL, Qdrant, or Neo4j directly.
- Use TDD for code tasks and commit after every independently testable task.
- Docker Desktop with Compose support is required for PostgreSQL and Neo4j integration tests. Unit tests must remain runnable without Docker.

---

## Planned File Map

| Path | Responsibility |
| --- | --- |
| `pyproject.toml` | Python dependencies, lint, type-check, and test configuration |
| `.env.example` | Local service configuration without secrets |
| `compose.yaml` | PostgreSQL, Qdrant, and Neo4j development services |
| `src/skillforge_kb/domain/enums.py` | Stable enums shared across all adapters |
| `src/skillforge_kb/domain/models.py` | Source, chunk, query, evidence, and report contracts |
| `src/skillforge_kb/domain/ports.py` | Repository, parser, encoder, graph, and index protocols |
| `src/skillforge_kb/config.py` | Validated application settings |
| `src/skillforge_kb/governance/policy.py` | Source admission and lifecycle rules |
| `src/skillforge_kb/governance/service.py` | Source registration and review transitions |
| `src/skillforge_kb/storage/postgres.py` | PostgreSQL connection and repositories |
| `src/skillforge_kb/storage/migrations/001_initial.sql` | Initial relational schema |
| `src/skillforge_kb/ingestion/fetch.py` | HTTP acquisition with allowlists and limits |
| `src/skillforge_kb/ingestion/loaders.py` | HTML and PDF parsing into normalized documents |
| `src/skillforge_kb/ingestion/normalize.py` | Text normalization, hashing, and deduplication |
| `src/skillforge_kb/ingestion/chunking.py` | Pedagogical semantic chunking |
| `src/skillforge_kb/ontology/catalog.py` | YAML ontology validation and concept lookup |
| `src/skillforge_kb/ontology/neo4j.py` | Neo4j graph publication and expansion |
| `src/skillforge_kb/index/qdrant.py` | Dense/sparse indexing and candidate retrieval |
| `src/skillforge_kb/retrieval/query.py` | Bilingual query normalization and concept candidates |
| `src/skillforge_kb/retrieval/fusion.py` | Reciprocal-rank fusion and deterministic scoring |
| `src/skillforge_kb/retrieval/service.py` | Three-channel retrieval and Evidence Package assembly |
| `src/skillforge_kb/api/app.py` | FastAPI application factory and routes |
| `src/skillforge_kb/api/schemas.py` | HTTP request and response schemas |
| `src/skillforge_kb/evaluation/dataset.py` | Retrieval benchmark loading and validation |
| `src/skillforge_kb/evaluation/metrics.py` | Recall, reciprocal rank, nDCG, parity, and latency metrics |
| `src/skillforge_kb/evaluation/runner.py` | Baseline and ablation runner |
| `src/skillforge_kb/cli.py` | Source, build, review, evaluate, and report commands |
| `resources/ontology/ai_v1.yaml` | Versioned bilingual concept catalog |
| `resources/sources/manifest.yaml` | Reviewed public-source registry |
| `resources/evaluation/retrieval_v1.jsonl` | Human-labeled retrieval benchmark |
| `tests/unit/` | Service-free unit tests |
| `tests/integration/` | PostgreSQL, Qdrant, Neo4j, and API integration tests |
| `docs/knowledge-base/` | Operator, curation, schema, rebuild, and evaluation documentation |

---

### Task 1: Establish the Python project and domain contracts

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `src/skillforge_kb/__init__.py`
- Create: `src/skillforge_kb/domain/__init__.py`
- Create: `src/skillforge_kb/domain/enums.py`
- Create: `src/skillforge_kb/domain/models.py`
- Create: `src/skillforge_kb/domain/ports.py`
- Create: `src/skillforge_kb/config.py`
- Test: `tests/unit/domain/test_models.py`

**Interfaces:**
- Consumes: none.
- Produces: `SourceRecord`, `Citation`, `EvidenceChunk`, `EvidenceQuery`, `EvidenceHit`, `EvidencePackage`, and repository/index protocols used by every later task.

- [ ] **Step 1: Write the failing domain validation tests**

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.domain.enums import Language, LicenseStatus, SourceTier
from skillforge_kb.domain.models import Citation, EvidenceChunk, SourceRecord


def test_source_requires_provenance_and_license_status() -> None:
    source = SourceRecord(
        source_id="d2l-en",
        title="Dive into Deep Learning",
        canonical_url="https://d2l.ai/",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=LicenseStatus.ALLOWED,
        license_url="https://d2l.ai/chapter_appendix-tools-for-deep-learning/notation.html",
        retrieved_at=datetime.now(UTC),
    )
    assert source.source_id == "d2l-en"


def test_published_chunk_requires_resolvable_locator() -> None:
    with pytest.raises(ValidationError, match="locator"):
        EvidenceChunk(
            chunk_id="chunk-1",
            source_id="d2l-en",
            concept_ids=["ml.supervised.logistic-regression"],
            language=Language.EN,
            content_kind="definition",
            text="Logistic regression models a conditional probability.",
            citation=Citation(url="https://d2l.ai/", locator=""),
            content_hash="a" * 64,
            reviewed=True,
        )
```

- [ ] **Step 2: Run the tests and verify the missing package failure**

Run: `uv run pytest tests/unit/domain/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'skillforge_kb'`.

- [ ] **Step 3: Create `pyproject.toml` with bounded dependencies and test configuration**

```toml
[project]
name = "skillforge-kb"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.116,<1",
  "uvicorn[standard]>=0.35,<1",
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.10,<3",
  "langchain-core>=0.3.68,<1",
  "langchain-community>=0.3.27,<1",
  "langchain-text-splitters>=0.3.8,<1",
  "qdrant-client[fastembed]>=1.14,<2",
  "neo4j>=5.28,<6",
  "psycopg[binary,pool]>=3.2.9,<4",
  "pymupdf>=1.26,<2",
  "trafilatura>=2.0,<3",
  "httpx>=0.28,<1",
  "pyyaml>=6.0,<7",
  "typer>=0.16,<1",
  "tenacity>=9.1,<10",
  "structlog>=25.4,<26",
]

[project.scripts]
skillforge-kb = "skillforge_kb.cli:app"

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
  "pytest>=8.4,<9",
  "pytest-asyncio>=1.0,<2",
  "respx>=0.22,<1",
  "ruff>=0.12,<1",
  "mypy>=1.16,<2",
  "testcontainers[postgres,neo4j]>=4.10,<5",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["integration: requires local services or Docker"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["skillforge_kb"]
```

- [ ] **Step 4: Implement stable enums and Pydantic contracts**

```python
# src/skillforge_kb/domain/enums.py
from enum import StrEnum


class Language(StrEnum):
    ZH = "zh"
    EN = "en"


class SourceTier(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class LicenseStatus(StrEnum):
    PENDING = "pending"
    ALLOWED = "allowed"
    METADATA_ONLY = "metadata_only"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    LICENSED = "licensed"
    PARSED = "parsed"
    AUTO_CHECKED = "auto_checked"
    HUMAN_REVIEWED = "human_reviewed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ContentKind(StrEnum):
    DEFINITION = "definition"
    DERIVATION = "derivation"
    CODE = "code"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    MISCONCEPTION = "misconception"
```

```python
# src/skillforge_kb/domain/models.py
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .enums import ContentKind, Language, LicenseStatus, ReviewStatus, SourceTier


class SourceRecord(BaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    title: str = Field(min_length=3)
    canonical_url: HttpUrl
    language: Language
    tier: SourceTier
    license_status: LicenseStatus
    license_url: HttpUrl | None = None
    retrieved_at: datetime
    version_label: str | None = None
    review_status: ReviewStatus = ReviewStatus.CANDIDATE

    @model_validator(mode="after")
    def validate_allowed_license(self) -> "SourceRecord":
        if self.license_status is LicenseStatus.ALLOWED and self.license_url is None:
            raise ValueError("allowed sources require license_url")
        return self


class Citation(BaseModel):
    url: HttpUrl
    locator: str = Field(min_length=1)
    title: str | None = None


class EvidenceChunk(BaseModel):
    chunk_id: str = Field(min_length=3)
    source_id: str
    concept_ids: list[str] = Field(min_length=1)
    language: Language
    content_kind: ContentKind
    text: str = Field(min_length=20)
    citation: Citation
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    difficulty: int = Field(default=2, ge=1, le=4)
    reviewed: bool = False
    derived: bool = False
    version_label: str | None = None


class EvidenceQuery(BaseModel):
    text: str = Field(min_length=2)
    language: Language | None = None
    concept_ids: list[str] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=1, le=4)
    top_k: int = Field(default=5, ge=1, le=20)


class EvidenceHit(BaseModel):
    chunk: EvidenceChunk
    sparse_score: float | None = None
    dense_score: float | None = None
    graph_score: float | None = None
    final_score: float = Field(ge=0)
    score_components: dict[str, float] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    query: EvidenceQuery
    normalized_queries: list[str]
    matched_concept_ids: list[str]
    hits: list[EvidenceHit]
    coverage_gap: bool = False
    conflicts: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Add validated environment settings**

```python
# src/skillforge_kb/config.py
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
```

Create the local configuration template with these exact keys:

```dotenv
# .env.example
SKILLFORGE_POSTGRES_DSN=postgresql://skillforge:skillforge@localhost:5432/skillforge
SKILLFORGE_QDRANT_URL=http://localhost:6333
SKILLFORGE_NEO4J_URI=bolt://localhost:7687
SKILLFORGE_NEO4J_USER=neo4j
SKILLFORGE_NEO4J_PASSWORD=skillforge-dev
SKILLFORGE_DENSE_MODEL=intfloat/multilingual-e5-large
SKILLFORGE_SPARSE_MODEL=Qdrant/bm25
SKILLFORGE_REQUEST_TIMEOUT_SECONDS=20
```

- [ ] **Step 6: Sync dependencies and run quality checks**

Run: `uv sync --all-groups`

Expected: exit 0 and `uv.lock` created.

Run: `uv run pytest tests/unit/domain/test_models.py -v`

Expected: 2 passed.

Run: `uv run ruff check src tests`

Expected: `All checks passed!`

Run: `uv run mypy src`

Expected: `Success: no issues found`.

Append these runtime artifacts to `.gitignore` while preserving `.superpowers/`:

```gitignore
.venv/
.env
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
data/raw/
data/build/
reports/generated/
```

- [ ] **Step 7: Commit the foundation**

```bash
git add .gitignore pyproject.toml uv.lock .env.example src tests/unit/domain
git commit -m "build: establish knowledge base domain contracts"
```

---

### Task 2: Implement source governance and lifecycle transitions

**Files:**
- Create: `src/skillforge_kb/governance/__init__.py`
- Create: `src/skillforge_kb/governance/policy.py`
- Create: `src/skillforge_kb/governance/service.py`
- Create: `src/skillforge_kb/storage/memory.py`
- Modify: `src/skillforge_kb/domain/ports.py`
- Test: `tests/unit/governance/test_policy.py`
- Test: `tests/unit/governance/test_service.py`

**Interfaces:**
- Consumes: `SourceRecord`, `LicenseStatus`, and `ReviewStatus` from Task 1.
- Produces: `SourceRepository`, `SourcePolicy.evaluate(source)`, and `SourceGovernanceService.transition(source_id, target)`.

- [ ] **Step 1: Write failing policy and state-transition tests**

```python
from datetime import UTC, datetime

import pytest

from skillforge_kb.domain.enums import Language, LicenseStatus, ReviewStatus, SourceTier
from skillforge_kb.domain.models import SourceRecord
from skillforge_kb.governance.policy import AdmissionDecision, SourcePolicy


def source(status: LicenseStatus) -> SourceRecord:
    return SourceRecord(
        source_id="source-1",
        title="Open course",
        canonical_url="https://example.edu/course",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=status,
        license_url="https://example.edu/license" if status is LicenseStatus.ALLOWED else None,
        retrieved_at=datetime.now(UTC),
    )


def test_allowed_source_can_enter_full_text_pipeline() -> None:
    assert SourcePolicy().evaluate(source(LicenseStatus.ALLOWED)) is AdmissionDecision.FULL_TEXT


def test_metadata_only_source_cannot_enter_full_text_pipeline() -> None:
    assert SourcePolicy().evaluate(source(LicenseStatus.METADATA_ONLY)) is AdmissionDecision.METADATA_ONLY


def test_published_transition_requires_human_review() -> None:
    with pytest.raises(ValueError, match="human_reviewed"):
        SourcePolicy().assert_transition(ReviewStatus.AUTO_CHECKED, ReviewStatus.PUBLISHED)
```

- [ ] **Step 2: Run tests and verify import failures**

Run: `uv run pytest tests/unit/governance -v`

Expected: FAIL because `skillforge_kb.governance.policy` does not exist.

- [ ] **Step 3: Implement the admission policy and explicit state machine**

```python
# src/skillforge_kb/governance/policy.py
from enum import StrEnum

from skillforge_kb.domain.enums import LicenseStatus, ReviewStatus
from skillforge_kb.domain.models import SourceRecord


class AdmissionDecision(StrEnum):
    FULL_TEXT = "full_text"
    METADATA_ONLY = "metadata_only"
    REJECT = "reject"


ALLOWED_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.CANDIDATE: {ReviewStatus.LICENSED},
    ReviewStatus.LICENSED: {ReviewStatus.PARSED},
    ReviewStatus.PARSED: {ReviewStatus.AUTO_CHECKED},
    ReviewStatus.AUTO_CHECKED: {ReviewStatus.HUMAN_REVIEWED},
    ReviewStatus.HUMAN_REVIEWED: {ReviewStatus.PUBLISHED},
    ReviewStatus.PUBLISHED: {ReviewStatus.DEPRECATED},
    ReviewStatus.DEPRECATED: set(),
}


class SourcePolicy:
    def evaluate(self, source: SourceRecord) -> AdmissionDecision:
        if source.license_status is LicenseStatus.ALLOWED:
            return AdmissionDecision.FULL_TEXT
        if source.license_status is LicenseStatus.METADATA_ONLY:
            return AdmissionDecision.METADATA_ONLY
        return AdmissionDecision.REJECT

    def assert_transition(self, current: ReviewStatus, target: ReviewStatus) -> None:
        if target not in ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"invalid source transition: {current} -> {target}; human_reviewed required")
```

- [ ] **Step 4: Define the repository protocol and governance service**

```python
# src/skillforge_kb/domain/ports.py
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from .models import EvidenceChunk, SourceRecord


class SourceRepository(Protocol):
    def get(self, source_id: str) -> SourceRecord | None: ...
    def save(self, source: SourceRecord) -> None: ...
    def list_all(self) -> list[SourceRecord]: ...


class ChunkRepository(Protocol):
    def save_many(self, chunks: list[EvidenceChunk]) -> None: ...
    def get_many(self, chunk_ids: list[str]) -> list[EvidenceChunk]: ...
```

```python
# src/skillforge_kb/governance/service.py
from skillforge_kb.domain.enums import ReviewStatus
from skillforge_kb.domain.models import SourceRecord
from skillforge_kb.domain.ports import SourceRepository

from .policy import SourcePolicy


class SourceGovernanceService:
    def __init__(self, repository: SourceRepository, policy: SourcePolicy) -> None:
        self.repository = repository
        self.policy = policy

    def register(self, source: SourceRecord) -> None:
        if self.repository.get(source.source_id) is not None:
            raise ValueError(f"source already exists: {source.source_id}")
        self.repository.save(source)

    def transition(self, source_id: str, target: ReviewStatus) -> SourceRecord:
        source = self.repository.get(source_id)
        if source is None:
            raise KeyError(source_id)
        self.policy.assert_transition(source.review_status, target)
        updated = source.model_copy(update={"review_status": target})
        self.repository.save(updated)
        return updated
```

Create the service-free repository used by unit tests:

```python
# src/skillforge_kb/storage/memory.py
from skillforge_kb.domain.models import SourceRecord


class InMemorySourceRepository:
    def __init__(self) -> None:
        self._sources: dict[str, SourceRecord] = {}

    def get(self, source_id: str) -> SourceRecord | None:
        return self._sources.get(source_id)

    def save(self, source: SourceRecord) -> None:
        self._sources[source.source_id] = source

    def list_all(self) -> list[SourceRecord]:
        return sorted(self._sources.values(), key=lambda item: item.source_id)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/governance -v`

Expected: all governance tests pass.

```bash
git add src/skillforge_kb/governance src/skillforge_kb/storage/memory.py src/skillforge_kb/domain/ports.py tests/unit/governance
git commit -m "feat: enforce source governance lifecycle"
```

---

### Task 3: Add local services and PostgreSQL repositories

**Files:**
- Create: `compose.yaml`
- Create: `src/skillforge_kb/storage/postgres.py`
- Create: `src/skillforge_kb/storage/migrations/001_initial.sql`
- Test: `tests/integration/storage/test_postgres.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `SourceRepository` and `ChunkRepository` from Task 2.
- Produces: `PostgresSourceRepository`, `PostgresChunkRepository`, and `apply_migrations(connection)`.

- [ ] **Step 1: Create the three-service development stack**

```yaml
# compose.yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: skillforge
      POSTGRES_USER: skillforge
      POSTGRES_PASSWORD: skillforge
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U skillforge -d skillforge"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes: ["postgres_data:/var/lib/postgresql/data"]
  qdrant:
    image: qdrant/qdrant:v1.14.1
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrant_data:/qdrant/storage"]
  neo4j:
    image: neo4j:5.26-community
    environment:
      NEO4J_AUTH: neo4j/skillforge-dev
    ports: ["7474:7474", "7687:7687"]
    volumes: ["neo4j_data:/data"]
volumes:
  postgres_data:
  qdrant_data:
  neo4j_data:
```

- [ ] **Step 2: Write the failing PostgreSQL round-trip test**

```python
import pytest

from skillforge_kb.storage.postgres import PostgresSourceRepository, apply_migrations


@pytest.mark.integration
def test_postgres_source_round_trip(postgres_connection, sample_source) -> None:
    apply_migrations(postgres_connection)
    repository = PostgresSourceRepository(postgres_connection)
    repository.save(sample_source)
    assert repository.get(sample_source.source_id) == sample_source
```

Create the integration fixture explicitly:

```python
# tests/integration/storage/conftest.py
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from skillforge_kb.domain.enums import Language, LicenseStatus, SourceTier
from skillforge_kb.domain.models import SourceRecord


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture
def postgres_connection(postgres_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(postgres_dsn) as connection:
        yield connection


@pytest.fixture
def sample_source() -> SourceRecord:
    return SourceRecord(
        source_id="sample-source",
        title="Sample open source",
        canonical_url="https://example.edu/source",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=LicenseStatus.ALLOWED,
        license_url="https://example.edu/license",
        retrieved_at=datetime.now(UTC),
    )
```

- [ ] **Step 3: Run the test against the started PostgreSQL service and verify failure**

Run: `docker compose up -d postgres`

Expected: PostgreSQL becomes healthy.

Run: `uv run pytest tests/integration/storage/test_postgres.py -v -m integration`

Expected: FAIL because `skillforge_kb.storage.postgres` does not exist.

- [ ] **Step 4: Create the relational schema**

```sql
-- src/skillforge_kb/storage/migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  payload JSONB NOT NULL,
  review_status TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_chunks (
  chunk_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  content_hash CHAR(64) NOT NULL,
  language TEXT NOT NULL,
  reviewed BOOLEAN NOT NULL DEFAULT FALSE,
  payload JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS evidence_chunks_content_hash_idx
ON evidence_chunks(content_hash);
```

- [ ] **Step 5: Implement parameterized JSONB repositories and idempotent migration execution**

Use this repository implementation. It uses parameterized SQL only and treats Pydantic JSON as the persisted contract:

```python
# src/skillforge_kb/storage/postgres.py
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from skillforge_kb.domain.models import EvidenceChunk, SourceRecord


MIGRATION_PATH = Path(__file__).parent / "migrations" / "001_initial.sql"


def apply_migrations(connection: psycopg.Connection) -> None:
    version = MIGRATION_PATH.stem
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cursor.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
        if cursor.fetchone() is None:
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            cursor.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
    connection.commit()


class PostgresSourceRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def get(self, source_id: str) -> SourceRecord | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT payload FROM sources WHERE source_id = %s", (source_id,))
            row = cursor.fetchone()
        return None if row is None else SourceRecord.model_validate(row["payload"])

    def save(self, source: SourceRecord) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sources(source_id, payload, review_status) VALUES (%s, %s, %s) "
                "ON CONFLICT(source_id) DO UPDATE SET payload = EXCLUDED.payload, "
                "review_status = EXCLUDED.review_status, updated_at = now()",
                (source.source_id, Jsonb(source.model_dump(mode="json")), source.review_status.value),
            )
        self.connection.commit()

    def list_all(self) -> list[SourceRecord]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT payload FROM sources ORDER BY source_id")
            return [SourceRecord.model_validate(row["payload"]) for row in cursor.fetchall()]


class PostgresChunkRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def save_many(self, chunks: list[EvidenceChunk]) -> None:
        rows = [
            (
                chunk.chunk_id,
                chunk.source_id,
                chunk.content_hash,
                chunk.language.value,
                chunk.reviewed,
                Jsonb(chunk.model_dump(mode="json")),
            )
            for chunk in chunks
        ]
        with self.connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO evidence_chunks"
                "(chunk_id, source_id, content_hash, language, reviewed, payload) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT(chunk_id) DO UPDATE SET content_hash = EXCLUDED.content_hash, "
                "language = EXCLUDED.language, reviewed = EXCLUDED.reviewed, "
                "payload = EXCLUDED.payload, updated_at = now()",
                rows,
            )
        self.connection.commit()

    def get_many(self, chunk_ids: list[str]) -> list[EvidenceChunk]:
        if not chunk_ids:
            return []
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT payload FROM evidence_chunks WHERE chunk_id = ANY(%s)",
                (chunk_ids,),
            )
            by_id = {
                chunk.chunk_id: chunk
                for chunk in (EvidenceChunk.model_validate(row["payload"]) for row in cursor.fetchall())
            }
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]
```

- [ ] **Step 6: Verify integration and commit**

Run: `uv run pytest tests/integration/storage/test_postgres.py -v -m integration`

Expected: PostgreSQL round-trip tests pass on two consecutive runs.

```bash
git add compose.yaml .env.example src/skillforge_kb/storage tests/integration/storage
git commit -m "feat: persist governed sources and chunks"
```

---

### Task 4: Acquire and parse governed HTML and PDF sources

**Files:**
- Create: `src/skillforge_kb/ingestion/__init__.py`
- Create: `src/skillforge_kb/ingestion/fetch.py`
- Create: `src/skillforge_kb/ingestion/loaders.py`
- Test: `tests/unit/ingestion/test_fetch.py`
- Test: `tests/unit/ingestion/test_loaders.py`

**Interfaces:**
- Consumes: admitted `SourceRecord` objects.
- Produces: `RawDocument(source_id, language, text, locator_prefix)` and `SourceFetcher.fetch(url)`.

- [ ] **Step 1: Write failing security and parser tests**

```python
import httpx
import pytest
import respx

from skillforge_kb.ingestion.fetch import SourceFetcher


@respx.mock
def test_fetch_rejects_redirect_to_unregistered_host() -> None:
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(302, headers={"location": "https://blocked.example/doc"})
    )
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"}, max_bytes=1024)
    with pytest.raises(ValueError, match="redirect host"):
        fetcher.fetch("https://allowed.example/doc")


@respx.mock
def test_fetch_rejects_oversized_response() -> None:
    respx.get("https://allowed.example/doc").mock(
        return_value=httpx.Response(200, content=b"x" * 2048)
    )
    fetcher = SourceFetcher(allowed_hosts={"allowed.example"}, max_bytes=1024)
    with pytest.raises(ValueError, match="size limit"):
        fetcher.fetch("https://allowed.example/doc")
```

- [ ] **Step 2: Run tests and verify missing module failure**

Run: `uv run pytest tests/unit/ingestion/test_fetch.py -v`

Expected: FAIL because ingestion modules do not exist.

- [ ] **Step 3: Implement bounded HTTP fetching**

Use a manual redirect loop so every redirect target is revalidated:

```python
# src/skillforge_kb/ingestion/fetch.py
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx


ACCEPTED_TYPES = {"text/html", "application/xhtml+xml", "application/pdf"}


@dataclass(frozen=True)
class FetchedResource:
    body: bytes
    final_url: str
    content_type: str


class SourceFetcher:
    def __init__(
        self,
        allowed_hosts: set[str],
        max_bytes: int = 20_000_000,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.allowed_hosts = {host.casefold() for host in allowed_hosts}
        self.max_bytes = max_bytes
        self.client = httpx.Client(timeout=timeout_seconds, follow_redirects=False)

    def _validate_url(self, url: str, redirect: bool = False) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("source URL must use HTTPS")
        if parsed.hostname is None or parsed.hostname.casefold() not in self.allowed_hosts:
            label = "redirect host" if redirect else "source host"
            raise ValueError(f"{label} is not registered")

    def fetch(self, url: str) -> FetchedResource:
        current = url
        self._validate_url(current)
        for redirect_count in range(4):
            response = self.client.get(current)
            if response.is_redirect:
                if redirect_count == 3:
                    raise ValueError("redirect limit exceeded")
                location = response.headers.get("location")
                if location is None:
                    raise ValueError("redirect missing location")
                current = urljoin(current, location)
                self._validate_url(current, redirect=True)
                continue
            response.raise_for_status()
            declared = response.headers.get("content-length")
            if declared is not None and int(declared) > self.max_bytes:
                raise ValueError("response exceeds size limit")
            body = response.content
            if len(body) > self.max_bytes:
                raise ValueError("response exceeds size limit")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            if content_type not in ACCEPTED_TYPES:
                raise ValueError(f"unsupported content type: {content_type}")
            return FetchedResource(body, str(response.url), content_type)
        raise ValueError("redirect loop did not terminate")
```

- [ ] **Step 4: Implement HTML and PDF loaders behind one protocol**

```python
# src/skillforge_kb/ingestion/loaders.py
from dataclasses import dataclass

import fitz
import trafilatura

from skillforge_kb.domain.enums import Language


@dataclass(frozen=True)
class RawDocument:
    source_id: str
    language: Language
    text: str
    locator_prefix: str


def load_html(source_id: str, language: Language, content: bytes, url: str) -> RawDocument:
    text = trafilatura.extract(content, include_links=False, include_tables=True)
    if text is None or len(text.strip()) < 100:
        raise ValueError("HTML extraction produced insufficient content")
    return RawDocument(source_id, language, text.strip(), url)


def load_pdf(source_id: str, language: Language, content: bytes, url: str) -> list[RawDocument]:
    pdf = fitz.open(stream=content, filetype="pdf")
    pages: list[RawDocument] = []
    for page_number, page in enumerate(pdf, start=1):
        text = page.get_text("text").strip()
        if text:
            pages.append(RawDocument(source_id, language, text, f"{url}#page={page_number}"))
    if not pages:
        raise ValueError("PDF extraction produced no text")
    return pages
```

- [ ] **Step 5: Test malformed, empty, and valid documents**

Add these concrete parser tests:

```python
import fitz

from skillforge_kb.domain.enums import Language
from skillforge_kb.ingestion.loaders import load_html, load_pdf


def test_pdf_loader_preserves_page_locators() -> None:
    document = fitz.open()
    for page_number in (1, 2):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {page_number} explains attention with enough content for parsing.")
    pages = load_pdf("paper", Language.EN, document.tobytes(), "https://example.edu/paper.pdf")
    assert [page.locator_prefix for page in pages] == [
        "https://example.edu/paper.pdf#page=1",
        "https://example.edu/paper.pdf#page=2",
    ]


def test_html_loader_extracts_main_content() -> None:
    html = b"""
    <html><body><nav>Home About Contact</nav><main><h1>Logistic Regression</h1>
    <p>Logistic regression estimates conditional class probabilities using the sigmoid function.</p>
    <p>Its loss is binary cross entropy and its decision boundary is linear in the input features.</p>
    </main></body></html>
    """
    document = load_html("course", Language.EN, html, "https://example.edu/course")
    assert "conditional class probabilities" in document.text
    assert "Home About Contact" not in document.text
```

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/ingestion -v`

Expected: fetch and loader tests pass.

```bash
git add src/skillforge_kb/ingestion tests/unit/ingestion
git commit -m "feat: acquire and parse governed public sources"
```

---

### Task 5: Normalize, deduplicate, and pedagogically chunk content

**Files:**
- Create: `src/skillforge_kb/ingestion/normalize.py`
- Create: `src/skillforge_kb/ingestion/chunking.py`
- Test: `tests/unit/ingestion/test_normalize.py`
- Test: `tests/unit/ingestion/test_chunking.py`

**Interfaces:**
- Consumes: `RawDocument` from Task 4.
- Produces: deterministic content hashes and draft `EvidenceChunk` records with citation locators preserved.

- [ ] **Step 1: Write failing normalization and boundary tests**

```python
from skillforge_kb.ingestion.normalize import normalize_text, sha256_text


def test_normalization_is_stable_across_line_endings_and_unicode_spaces() -> None:
    left = "Logistic\r\nregression\u00a0model"
    right = "Logistic\nregression model"
    assert normalize_text(left) == normalize_text(right)
    assert sha256_text(left) == sha256_text(right)
```

```python
from skillforge_kb.ingestion.chunking import PedagogicalChunker


def test_definition_heading_stays_with_definition_body() -> None:
    text = (
        "## Definition\nLogistic regression estimates conditional class probability "
        "with a sigmoid applied to a linear combination of input features.\n"
        "## Example\nUse the sigmoid output as the positive-class probability in binary classification."
    )
    chunks = PedagogicalChunker(chunk_size=180, overlap=20).split(text)
    assert chunks[0].startswith("## Definition")
    assert "estimates class probability" in chunks[0]
```

- [ ] **Step 2: Run tests and verify missing function failures**

Run: `uv run pytest tests/unit/ingestion/test_normalize.py tests/unit/ingestion/test_chunking.py -v`

Expected: FAIL on missing modules.

- [ ] **Step 3: Implement deterministic normalization and hashing**

Use this exact normalizer and hash function:

```python
# src/skillforge_kb/ingestion/normalize.py
import hashlib
import re
import unicodedata


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ")
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implement structure-first chunking**

Use a structure-first wrapper around LangChain's splitter:

```python
# src/skillforge_kb/ingestion/chunking.py
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter


HEADING = re.compile(r"(?m)(?=^#{1,6}\s)")


class PedagogicalChunker:
    def __init__(self, chunk_size: int = 900, overlap: int = 120) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", "。", ". ", " ", ""],
            length_function=len,
        )

    def split(self, text: str) -> list[str]:
        sections = [section.strip() for section in HEADING.split(text) if section.strip()]
        chunks: list[str] = []
        for section in sections or [text.strip()]:
            if section.startswith("```") and section.endswith("```") and len(section) <= 2_000:
                candidates = [section]
            else:
                candidates = self.splitter.split_text(section)
            chunks.extend(candidate for candidate in candidates if len(candidate) >= 80)
        return chunks
```

- [ ] **Step 5: Add duplicate classification**

Add explicit duplicate functions; source-priority selection remains in the build service and records the rejected chunk in its report:

```python
# append to src/skillforge_kb/ingestion/normalize.py
def ngrams(text: str, width: int = 5) -> set[str]:
    value = normalize_text(text).casefold()
    return {value[index : index + width] for index in range(max(0, len(value) - width + 1))}


def jaccard_similarity(left: str, right: str) -> float:
    left_grams = ngrams(left)
    right_grams = ngrams(right)
    union = left_grams | right_grams
    if not union:
        return 1.0
    return len(left_grams & right_grams) / len(union)


def is_near_duplicate(left: str, right: str, threshold: float = 0.92) -> bool:
    return jaccard_similarity(left, right) >= threshold
```

- [ ] **Step 6: Verify unit tests and commit**

Run: `uv run pytest tests/unit/ingestion -v`

Expected: all ingestion unit tests pass.

```bash
git add src/skillforge_kb/ingestion tests/unit/ingestion
git commit -m "feat: create deterministic pedagogical chunks"
```

---

### Task 6: Build and publish the bilingual concept ontology

**Files:**
- Create: `resources/ontology/ai_v1.yaml`
- Create: `src/skillforge_kb/ontology/__init__.py`
- Create: `src/skillforge_kb/ontology/catalog.py`
- Create: `src/skillforge_kb/ontology/neo4j.py`
- Modify: `src/skillforge_kb/domain/ports.py`
- Test: `tests/unit/ontology/test_catalog.py`
- Test: `tests/integration/ontology/test_neo4j.py`

**Interfaces:**
- Consumes: concept IDs attached to draft chunks.
- Produces: `OntologyCatalog.get/resolve_alias/prerequisites`, `Neo4jConceptGraph.publish`, and `Neo4jConceptGraph.expand`.

- [ ] **Step 1: Add a valid seed ontology for the three deep modules**

```yaml
version: ai-v1
concepts:
  - id: math.probability.conditional-probability
    names: {zh: 条件概率, en: Conditional Probability}
    aliases: [conditional probability, 条件概率]
    module: mathematics
    difficulty: 1
    prerequisites: []
  - id: math.linear-algebra.vector
    names: {zh: 向量, en: Vector}
    aliases: [vector, 向量]
    module: mathematics
    difficulty: 1
    prerequisites: []
  - id: math.linear-algebra.matrix-multiplication
    names: {zh: 矩阵乘法, en: Matrix Multiplication}
    aliases: [matrix product, 矩阵乘积]
    module: mathematics
    difficulty: 1
    prerequisites: [math.linear-algebra.vector]
  - id: dl.representation.embedding
    names: {zh: 嵌入表示, en: Embedding Representation}
    aliases: [embedding, 词嵌入]
    module: deep_learning
    difficulty: 2
    prerequisites: [math.linear-algebra.vector]
  - id: dl.optimization.gradient-descent
    names: {zh: 梯度下降, en: Gradient Descent}
    aliases: [gradient descent, 梯度下降法]
    module: deep_learning
    difficulty: 2
    prerequisites: [math.linear-algebra.vector]
  - id: ml.retrieval.vector-search
    names: {zh: 向量检索, en: Vector Search}
    aliases: [vector retrieval, 相似度检索]
    module: classical_ml
    difficulty: 3
    prerequisites: [math.linear-algebra.vector]
  - id: ml.supervised.logistic-regression
    names: {zh: 逻辑回归, en: Logistic Regression}
    aliases: [logit model, 对数几率回归]
    module: classical_ml
    difficulty: 2
    prerequisites: [math.probability.conditional-probability, math.linear-algebra.vector]
  - id: dl.transformer.self-attention
    names: {zh: 自注意力, en: Self-Attention}
    aliases: [scaled dot-product attention, 缩放点积注意力]
    module: transformer
    difficulty: 3
    prerequisites: [math.linear-algebra.matrix-multiplication, dl.representation.embedding]
  - id: llm.adaptation.peft
    names: {zh: 参数高效微调, en: Parameter-Efficient Fine-Tuning}
    aliases: [PEFT, LoRA]
    module: llm
    difficulty: 4
    prerequisites: [dl.transformer.self-attention, dl.optimization.gradient-descent]
  - id: llm.application.rag
    names: {zh: 检索增强生成, en: Retrieval-Augmented Generation}
    aliases: [RAG, 检索增强]
    module: llm
    difficulty: 4
    prerequisites: [dl.transformer.self-attention, ml.retrieval.vector-search]
```

- [ ] **Step 2: Write failing catalog validation tests**

Test duplicate IDs, duplicate aliases within one language, missing bilingual names, dangling prerequisites, cycles in `PREREQUISITE_OF`, and valid alias resolution for `RAG` and `检索增强`.

- [ ] **Step 3: Implement strict YAML loading and cycle detection**

Implement the validated catalog and cycle check:

```python
# src/skillforge_kb/ontology/catalog.py
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from skillforge_kb.ingestion.normalize import normalize_text


class Concept(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]+$")
    names: dict[str, str]
    aliases: list[str] = Field(default_factory=list)
    module: str
    difficulty: int = Field(ge=1, le=4)
    prerequisites: list[str] = Field(default_factory=list)


class OntologyDocument(BaseModel):
    version: str
    concepts: list[Concept]


def normalize_alias(value: str) -> str:
    return normalize_text(value).casefold()


class OntologyCatalog:
    def __init__(self, document: OntologyDocument) -> None:
        self.version = document.version
        self.concepts = {concept.id: concept for concept in document.concepts}
        if len(self.concepts) != len(document.concepts):
            raise ValueError("duplicate concept IDs")
        self._aliases: dict[str, str] = {}
        for concept in document.concepts:
            if set(concept.names) != {"zh", "en"}:
                raise ValueError(f"concept requires zh and en names: {concept.id}")
            for value in [*concept.names.values(), *concept.aliases]:
                key = normalize_alias(value)
                owner = self._aliases.get(key)
                if owner is not None and owner != concept.id:
                    raise ValueError(f"duplicate alias: {value}")
                self._aliases[key] = concept.id
            for prerequisite in concept.prerequisites:
                if prerequisite not in self.concepts:
                    raise ValueError(f"dangling prerequisite: {prerequisite}")
        self._assert_acyclic()

    @classmethod
    def load(cls, path: Path) -> "OntologyCatalog":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(OntologyDocument.model_validate(raw))

    def resolve_alias(self, value: str) -> str | None:
        return self._aliases.get(normalize_alias(value))

    def get(self, concept_id: str) -> Concept:
        return self.concepts[concept_id]

    def prerequisites(self, concept_id: str) -> list[str]:
        return list(self.concepts[concept_id].prerequisites)

    def _assert_acyclic(self) -> None:
        gray: set[str] = set()
        black: set[str] = set()

        def visit(concept_id: str) -> None:
            if concept_id in black:
                return
            if concept_id in gray:
                raise ValueError(f"prerequisite cycle at {concept_id}")
            gray.add(concept_id)
            for prerequisite in self.concepts[concept_id].prerequisites:
                visit(prerequisite)
            gray.remove(concept_id)
            black.add(concept_id)

        for concept_id in self.concepts:
            visit(concept_id)
```

- [ ] **Step 4: Write the failing Neo4j publish/expand integration test**

Publish the seed ontology twice and assert idempotent node counts. Expand `llm.application.rag` by `PREREQUISITE_OF` with depth 1 and assert `dl.transformer.self-attention` appears while an unrelated concept does not.

- [ ] **Step 5: Implement parameterized Neo4j writes and bounded expansion**

Add a graph protocol and a bounded Neo4j adapter:

```python
# append to src/skillforge_kb/domain/ports.py
class ConceptGraph(Protocol):
    def expand(
        self,
        concept_ids: list[str],
        relation_types: set[str],
        max_depth: int,
    ) -> list[str]: ...
```

```python
# src/skillforge_kb/ontology/neo4j.py
from neo4j import Driver

from .catalog import OntologyCatalog


ALLOWED_RELATIONS = {
    "PREREQUISITE_OF",
    "PART_OF",
    "CONTRASTS_WITH",
    "CONFUSED_WITH",
}


class Neo4jConceptGraph:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def publish(self, catalog: OntologyCatalog) -> None:
        rows = [
            {
                "id": concept.id,
                "zh": concept.names["zh"],
                "en": concept.names["en"],
                "module": concept.module,
                "difficulty": concept.difficulty,
                "version": catalog.version,
            }
            for concept in catalog.concepts.values()
        ]
        edges = [
            {"source": prerequisite, "target": concept.id}
            for concept in catalog.concepts.values()
            for prerequisite in concept.prerequisites
        ]
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT concept_id IF NOT EXISTS "
                "FOR (concept:Concept) REQUIRE concept.id IS UNIQUE"
            ).consume()
            session.run(
                "UNWIND $rows AS row MERGE (c:Concept {id: row.id}) "
                "SET c.zh = row.zh, c.en = row.en, c.module = row.module, "
                "c.difficulty = row.difficulty, c.version = row.version",
                rows=rows,
            ).consume()
            session.run(
                "UNWIND $edges AS edge MATCH (a:Concept {id: edge.source}) "
                "MATCH (b:Concept {id: edge.target}) "
                "MERGE (a)-[:PREREQUISITE_OF]->(b)",
                edges=edges,
            ).consume()

    def expand(
        self,
        concept_ids: list[str],
        relation_types: set[str],
        max_depth: int,
    ) -> list[str]:
        if max_depth not in {1, 2}:
            raise ValueError("max_depth must be 1 or 2")
        if not relation_types or not relation_types <= ALLOWED_RELATIONS:
            raise ValueError("unsupported graph relation")
        query = (
            f"MATCH (start:Concept)-[path*1..{max_depth}]-(related:Concept) "
            "WHERE start.id IN $concept_ids "
            "AND ALL(rel IN path WHERE type(rel) IN $relation_types) "
            "RETURN DISTINCT related.id AS id ORDER BY id LIMIT 20"
        )
        with self.driver.session() as session:
            result = session.run(
                query,
                concept_ids=concept_ids,
                relation_types=sorted(relation_types),
            )
            return [record["id"] for record in result]
```

- [ ] **Step 6: Verify and commit**

Run: `uv run pytest tests/unit/ontology -v`

Expected: catalog tests pass without services.

Run: `uv run pytest tests/integration/ontology/test_neo4j.py -v -m integration`

Expected: Neo4j idempotency and bounded expansion tests pass.

```bash
git add resources/ontology src/skillforge_kb/ontology tests/unit/ontology tests/integration/ontology
git commit -m "feat: publish bilingual AI concept ontology"
```

---

### Task 7: Implement dense and sparse Qdrant indexing

**Files:**
- Create: `src/skillforge_kb/index/__init__.py`
- Create: `src/skillforge_kb/index/qdrant.py`
- Modify: `src/skillforge_kb/domain/ports.py`
- Test: `tests/unit/index/test_qdrant.py`
- Test: `tests/integration/index/test_qdrant_service.py`

**Interfaces:**
- Consumes: reviewed `EvidenceChunk` records.
- Produces: `EvidenceIndex.upsert(chunks)`, `search_sparse(query, limit)`, and `search_dense(query, limit)` returning channel-specific ranked IDs and scores.

- [ ] **Step 1: Extend the index protocol**

```python
from dataclasses import dataclass
from typing import Protocol

from .models import EvidenceChunk, EvidenceQuery


@dataclass(frozen=True)
class RankedCandidate:
    chunk_id: str
    score: float
    channel: str


class EvidenceIndex(Protocol):
    def upsert(self, chunks: list[EvidenceChunk]) -> None: ...
    def search_sparse(self, query: EvidenceQuery, limit: int) -> list[RankedCandidate]: ...
    def search_dense(self, query: EvidenceQuery, limit: int) -> list[RankedCandidate]: ...
```

- [ ] **Step 2: Write failing local-mode Qdrant tests**

Use `QdrantClient(":memory:")` with these deterministic test encoders. Insert one Chinese and one English chunk for the same concept. Assert idempotent upsert, metadata filters, separate channel scores, and rejection of unreviewed chunks.

```python
class FakeDenseEncoder:
    size = 3

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[float("attention" in text.casefold()), float("回归" in text), 1.0] for text in texts]


class FakeSparseEncoder:
    def encode(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        return [([1, 2], [float(len(text)), 1.0]) for text in texts]
```

- [ ] **Step 3: Create named dense and sparse vectors**

Create collection `skillforge_evidence_v1` with named vectors `dense` and `sparse`. Store only `chunk_id`, `source_id`, `concept_ids`, `language`, `difficulty`, `content_kind`, `reviewed`, and `version_label` in Qdrant payloads; PostgreSQL remains the source of truth for full chunks.

```python
# src/skillforge_kb/index/qdrant.py
from typing import Protocol

from qdrant_client import QdrantClient, models

from skillforge_kb.domain.models import EvidenceChunk, EvidenceQuery
from skillforge_kb.domain.ports import RankedCandidate


class DenseEncoder(Protocol):
    size: int
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SparseEncoder(Protocol):
    def encode(self, texts: list[str]) -> list[tuple[list[int], list[float]]]: ...


class QdrantEvidenceIndex:
    def __init__(
        self,
        client: QdrantClient,
        dense_encoder: DenseEncoder,
        sparse_encoder: SparseEncoder,
        collection: str = "skillforge_evidence_v1",
    ) -> None:
        self.client = client
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        self.collection = collection

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.dense_encoder.size,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            },
        )

    def upsert(self, chunks: list[EvidenceChunk]) -> None:
        if any(not chunk.reviewed for chunk in chunks):
            raise ValueError("unreviewed chunks cannot be indexed")
        self.ensure_collection()
        texts = [chunk.text for chunk in chunks]
        dense_vectors = self.dense_encoder.encode(texts)
        sparse_vectors = self.sparse_encoder.encode(texts)
        points = []
        for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors, strict=True):
            payload = {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "concept_ids": chunk.concept_ids,
                "language": chunk.language.value,
                "difficulty": chunk.difficulty,
                "content_kind": chunk.content_kind.value,
                "reviewed": chunk.reviewed,
                "version_label": chunk.version_label,
            }
            points.append(
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, chunk.chunk_id)),
                    vector={
                        "dense": dense,
                        "sparse": models.SparseVector(indices=sparse[0], values=sparse[1]),
                    },
                    payload=payload,
                )
            )
        self.client.upsert(self.collection, points=points, wait=True)

    def _filter(self, query: EvidenceQuery) -> models.Filter:
        conditions: list[models.Condition] = [
            models.FieldCondition(key="reviewed", match=models.MatchValue(value=True))
        ]
        if query.language is not None:
            conditions.append(
                models.FieldCondition(
                    key="language",
                    match=models.MatchValue(value=query.language.value),
                )
            )
        if query.difficulty is not None:
            conditions.append(
                models.FieldCondition(
                    key="difficulty",
                    match=models.MatchValue(value=query.difficulty),
                )
            )
        if query.concept_ids:
            conditions.append(
                models.FieldCondition(
                    key="concept_ids",
                    match=models.MatchAny(any=query.concept_ids),
                )
            )
        return models.Filter(must=conditions)

    def search_dense(self, query: EvidenceQuery, limit: int) -> list[RankedCandidate]:
        vector = self.dense_encoder.encode([query.text])[0]
        points = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            using="dense",
            query_filter=self._filter(query),
            with_payload=["chunk_id"],
            limit=limit,
        ).points
        return [
            RankedCandidate(str(point.payload["chunk_id"]), point.score, "dense")
            for point in points
        ]

    def search_sparse(self, query: EvidenceQuery, limit: int) -> list[RankedCandidate]:
        indices, values = self.sparse_encoder.encode([query.text])[0]
        points = self.client.query_points(
            collection_name=self.collection,
            query=models.SparseVector(indices=indices, values=values),
            using="sparse",
            query_filter=self._filter(query),
            with_payload=["chunk_id"],
            limit=limit,
        ).points
        return [
            RankedCandidate(str(point.payload["chunk_id"]), point.score, "sparse")
            for point in points
        ]
```

- [ ] **Step 4: Implement production encoders**

Wrap FastEmbed models behind the testable protocols. Determine `size` from one probe embedding at startup, batch at most 32 texts, and retain model names for the collection metadata check:

```python
from fastembed import SparseTextEmbedding, TextEmbedding


class FastEmbedDenseEncoder:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-large") -> None:
        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name)
        self.size = len(next(iter(self.model.embed(["dimension probe"]))))

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.model.embed(texts, batch_size=32)]


class FastEmbedSparseEncoder:
    def __init__(self, model_name: str = "Qdrant/bm25") -> None:
        self.model_name = model_name
        self.model = SparseTextEmbedding(model_name=model_name)

    def encode(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        return [
            (embedding.indices.tolist(), embedding.values.tolist())
            for embedding in self.model.embed(texts, batch_size=32)
        ]
```

- [ ] **Step 5: Verify local and service-backed tests**

Run: `uv run pytest tests/unit/index/test_qdrant.py -v`

Expected: unit tests pass without Docker.

Run: `docker compose up -d qdrant`

Run: `uv run pytest tests/integration/index/test_qdrant_service.py -v -m integration`

Expected: service-backed upsert and retrieval tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/skillforge_kb/index src/skillforge_kb/domain/ports.py tests/unit/index tests/integration/index
git commit -m "feat: index bilingual evidence with hybrid vectors"
```

---

### Task 8: Assemble three-channel retrieval and evidence packages

**Files:**
- Create: `src/skillforge_kb/retrieval/__init__.py`
- Create: `src/skillforge_kb/retrieval/query.py`
- Create: `src/skillforge_kb/retrieval/fusion.py`
- Create: `src/skillforge_kb/retrieval/service.py`
- Test: `tests/unit/retrieval/test_query.py`
- Test: `tests/unit/retrieval/test_fusion.py`
- Test: `tests/unit/retrieval/test_service.py`

**Interfaces:**
- Consumes: `EvidenceIndex`, `ChunkRepository`, `OntologyCatalog`, and `ConceptGraph` ports.
- Produces: `EvidenceService.retrieve(query: EvidenceQuery) -> EvidencePackage`.

- [ ] **Step 1: Write failing reciprocal-rank fusion tests**

```python
from skillforge_kb.domain.ports import RankedCandidate
from skillforge_kb.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_rewards_candidates_present_in_multiple_channels() -> None:
    sparse = [RankedCandidate("a", 1.0, "sparse"), RankedCandidate("b", 0.8, "sparse")]
    dense = [RankedCandidate("b", 0.9, "dense"), RankedCandidate("c", 0.7, "dense")]
    fused = reciprocal_rank_fusion([sparse, dense], k=60)
    assert fused[0].chunk_id == "b"
    assert fused[0].score > fused[1].score
```

- [ ] **Step 2: Implement deterministic query normalization**

Normalize NFKC, whitespace, ASCII case, acronym aliases, and ontology aliases. Emit the original query, normalized query, and at most three language variants. Do not use an LLM in v1 query normalization; this keeps retrieval evaluation deterministic.

```python
# src/skillforge_kb/retrieval/query.py
from dataclasses import dataclass

from skillforge_kb.ingestion.normalize import normalize_text
from skillforge_kb.ontology.catalog import OntologyCatalog


@dataclass(frozen=True)
class NormalizedQuery:
    variants: list[str]
    concept_ids: list[str]


def normalize_query(text: str, catalog: OntologyCatalog) -> NormalizedQuery:
    normalized = normalize_text(text)
    concept_ids = sorted(
        {
            concept_id
            for token in normalized.replace("?", " ").replace("？", " ").split()
            if (concept_id := catalog.resolve_alias(token)) is not None
        }
    )
    variants = [normalized]
    for concept_id in concept_ids:
        concept = catalog.concepts[concept_id]
        variants.extend([concept.names["zh"], concept.names["en"]])
    return NormalizedQuery(list(dict.fromkeys(variants))[:3], concept_ids)
```

- [ ] **Step 3: Implement RRF and final scoring**

Use this RRF implementation. The service then calculates final score from normalized RRF relevance (60%), source tier (15%), difficulty match (10%), freshness (5%), language diversity (5%), and non-duplicate diversity (5%).

```python
# src/skillforge_kb/retrieval/fusion.py
from dataclasses import dataclass

from skillforge_kb.domain.ports import RankedCandidate


@dataclass(frozen=True)
class FusedCandidate:
    chunk_id: str
    score: float
    channel_scores: dict[str, float]


def reciprocal_rank_fusion(
    ranked_lists: list[list[RankedCandidate]],
    k: int = 60,
) -> list[FusedCandidate]:
    scores: dict[str, float] = {}
    channels: dict[str, dict[str, float]] = {}
    for ranked_list in ranked_lists:
        for rank, candidate in enumerate(ranked_list, start=1):
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (k + rank)
            channels.setdefault(candidate.chunk_id, {})[candidate.channel] = candidate.score
    return [
        FusedCandidate(chunk_id, score, channels[chunk_id])
        for chunk_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]
```

- [ ] **Step 4: Implement the service orchestration**

The service requests `max(top_k * 4, 20)` candidates from sparse and dense channels, expands at most 20 graph concepts with depth 1, then assembles scored hits:

```python
# src/skillforge_kb/retrieval/service.py
from datetime import UTC, datetime

from skillforge_kb.domain.enums import ReviewStatus, SourceTier
from skillforge_kb.domain.models import EvidenceHit, EvidencePackage, EvidenceQuery
from skillforge_kb.domain.ports import ChunkRepository, ConceptGraph, EvidenceIndex, SourceRepository
from skillforge_kb.ontology.catalog import OntologyCatalog

from .fusion import reciprocal_rank_fusion
from .query import normalize_query


TIER_SCORE = {SourceTier.S1: 1.0, SourceTier.S2: 0.7, SourceTier.S3: 0.3}


class EvidenceService:
    def __init__(
        self,
        index: EvidenceIndex,
        chunks: ChunkRepository,
        sources: SourceRepository,
        catalog: OntologyCatalog,
        graph: ConceptGraph,
    ) -> None:
        self.index = index
        self.chunks = chunks
        self.sources = sources
        self.catalog = catalog
        self.graph = graph

    def retrieve(self, query: EvidenceQuery) -> EvidencePackage:
        normalized = normalize_query(query.text, self.catalog)
        concept_ids = sorted(set(query.concept_ids) | set(normalized.concept_ids))
        graph_unavailable = False
        if concept_ids:
            try:
                related = self.graph.expand(concept_ids, {"PREREQUISITE_OF", "PART_OF"}, 1)
                concept_ids = sorted(set(concept_ids) | set(related))[:20]
            except Exception:
                graph_unavailable = True
        candidate_limit = max(query.top_k * 4, 20)
        ranked_lists = []
        for variant in normalized.variants:
            channel_query = query.model_copy(update={"text": variant, "concept_ids": concept_ids})
            ranked_lists.append(self.index.search_sparse(channel_query, candidate_limit))
            ranked_lists.append(self.index.search_dense(channel_query, candidate_limit))
        fused = reciprocal_rank_fusion(ranked_lists)
        by_id = {chunk.chunk_id: chunk for chunk in self.chunks.get_many([item.chunk_id for item in fused])}
        max_rrf = fused[0].score if fused else 1.0
        hits: list[EvidenceHit] = []
        for item in fused:
            chunk = by_id.get(item.chunk_id)
            if chunk is None or not chunk.reviewed:
                continue
            source = self.sources.get(chunk.source_id)
            if source is None or source.review_status is not ReviewStatus.PUBLISHED:
                continue
            relevance = item.score / max_rrf
            authority = TIER_SCORE[source.tier]
            difficulty = 1.0 if query.difficulty is None else 1.0 / (1 + abs(chunk.difficulty - query.difficulty))
            age_days = max(0, (datetime.now(UTC) - source.retrieved_at).days)
            freshness = max(0.0, 1.0 - age_days / 730.0)
            language_diversity = 1.0 if query.language is None or chunk.language is not query.language else 0.5
            diversity = 1.0
            components = {
                "relevance": relevance,
                "authority": authority,
                "difficulty": difficulty,
                "freshness": freshness,
                "language_diversity": language_diversity,
                "diversity": diversity,
            }
            final_score = (
                0.60 * relevance
                + 0.15 * authority
                + 0.10 * difficulty
                + 0.05 * freshness
                + 0.05 * language_diversity
                + 0.05 * diversity
            )
            flags = ["graph_channel_unavailable"] if graph_unavailable else []
            hits.append(
                EvidenceHit(
                    chunk=chunk,
                    sparse_score=item.channel_scores.get("sparse"),
                    dense_score=item.channel_scores.get("dense"),
                    final_score=final_score,
                    score_components=components,
                    risk_flags=flags,
                )
            )
        hits.sort(key=lambda hit: (-hit.final_score, hit.chunk.chunk_id))
        selected = hits[: query.top_k]
        versions_by_concept: dict[str, set[str]] = {}
        for hit in selected:
            for concept_id in hit.chunk.concept_ids:
                if hit.chunk.version_label is not None:
                    versions_by_concept.setdefault(concept_id, set()).add(hit.chunk.version_label)
        conflicts = [
            f"version conflict for {concept_id}: {sorted(versions)}"
            for concept_id, versions in versions_by_concept.items()
            if len(versions) > 1
        ]
        return EvidencePackage(
            query=query,
            normalized_queries=normalized.variants,
            matched_concept_ids=concept_ids,
            hits=selected,
            coverage_gap=not selected,
            conflicts=conflicts,
        )
```

- [ ] **Step 5: Implement explicit failure behavior**

The service code above returns `coverage_gap=True` when no reviewed hit remains, records a version conflict for the same concept, and marks every returned hit with `graph_channel_unavailable` when graph expansion fails. Add focused tests that use fake ports to exercise all three branches; do not catch Qdrant failures in this layer because the API maps those dependency failures to HTTP 503.

- [ ] **Step 6: Run unit tests and commit**

Run: `uv run pytest tests/unit/retrieval -v`

Expected: query normalization, RRF, ranking, graph degradation, conflict, and coverage-gap tests pass.

```bash
git add src/skillforge_kb/retrieval tests/unit/retrieval
git commit -m "feat: assemble traceable evidence packages"
```

---

### Task 9: Expose the versioned Evidence API

**Files:**
- Create: `src/skillforge_kb/api/__init__.py`
- Create: `src/skillforge_kb/api/schemas.py`
- Create: `src/skillforge_kb/api/app.py`
- Test: `tests/unit/api/test_evidence_route.py`
- Test: `tests/integration/api/test_evidence_contract.py`

**Interfaces:**
- Consumes: `EvidenceService.retrieve` from Task 8.
- Produces: `POST /api/v1/evidence/search`, `GET /api/v1/health`, and OpenAPI schemas for future LangGraph tools.

- [ ] **Step 1: Write the failing route contract test**

```python
from fastapi.testclient import TestClient

from skillforge_kb.api.app import create_app


def test_evidence_route_returns_versioned_package(fake_evidence_service) -> None:
    client = TestClient(create_app(fake_evidence_service))
    response = client.post(
        "/api/v1/evidence/search",
        json={"text": "What is self-attention?", "language": "en", "top_k": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["query"]["text"] == "What is self-attention?"
    assert body["hits"][0]["chunk"]["citation"]["locator"]
```

- [ ] **Step 2: Run test and verify missing route failure**

Run: `uv run pytest tests/unit/api/test_evidence_route.py -v`

Expected: FAIL because the API package does not exist.

- [ ] **Step 3: Implement strict request and response schemas**

Add `schema_version="1.0"`, reject extra request fields, enforce `top_k <= 20`, and reuse the domain response without dropping citation, scoring, version, or risk fields:

```python
# src/skillforge_kb/api/schemas.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from skillforge_kb.domain.enums import Language
from skillforge_kb.domain.models import EvidencePackage


class EvidenceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=2)
    language: Language | None = None
    concept_ids: list[str] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=1, le=4)
    top_k: int = Field(default=5, ge=1, le=20)


class EvidenceSearchResponse(EvidencePackage):
    schema_version: Literal["1.0"] = "1.0"


class ErrorResponse(BaseModel):
    code: str
    request_id: str
```

- [ ] **Step 4: Implement dependency-injected application creation**

Use constructor injection and explicit exception responses:

```python
# src/skillforge_kb/api/app.py
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from skillforge_kb.domain.models import EvidenceQuery
from skillforge_kb.retrieval.service import EvidenceService

from .schemas import ErrorResponse, EvidenceSearchRequest, EvidenceSearchResponse


def create_app(evidence_service: EvidenceService) -> FastAPI:
    app = FastAPI(title="SkillForge Evidence API", version="1.0.0")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "schema_version": "1.0"}

    @app.post(
        "/api/v1/evidence/search",
        response_model=EvidenceSearchResponse,
        responses={503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    def search(
        payload: EvidenceSearchRequest,
        request: Request,
    ) -> EvidenceSearchResponse | JSONResponse:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        try:
            package = evidence_service.retrieve(EvidenceQuery.model_validate(payload.model_dump()))
        except (ConnectionError, TimeoutError):
            return JSONResponse(
                status_code=503,
                content={"code": "dependency_unavailable", "request_id": request_id},
            )
        return EvidenceSearchResponse.model_validate(package.model_dump())

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "request_id": request_id},
        )

    return app
```

- [ ] **Step 5: Add consumer-driven contract fixtures**

Store these minimum contract fixtures under `tests/fixtures/contracts/evidence_v1/`; use a test helper to compare the response with `EvidenceSearchResponse.model_validate_json` and assert the route schema reference in `create_app(fake).openapi()`:

```json
{"text":"What is self-attention?","language":"en","concept_ids":["dl.transformer.self-attention"],"difficulty":3,"top_k":5}
```

```json
{"schema_version":"1.0","query":{"text":"What is self-attention?","language":"en","concept_ids":["dl.transformer.self-attention"],"difficulty":3,"top_k":5},"normalized_queries":["What is self-attention?","自注意力","Self-Attention"],"matched_concept_ids":["dl.transformer.self-attention"],"hits":[{"chunk":{"chunk_id":"attention-paper-p4","source_id":"attention-paper","concept_ids":["dl.transformer.self-attention"],"language":"en","content_kind":"definition","text":"Self-attention relates positions within one sequence to compute a representation of that sequence.","citation":{"url":"https://arxiv.org/abs/1706.03762","locator":"page 4","title":"Attention Is All You Need"},"content_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","difficulty":3,"reviewed":true,"derived":false,"version_label":"v1"},"sparse_score":0.8,"dense_score":0.9,"graph_score":null,"final_score":0.91,"score_components":{"relevance":1.0,"authority":1.0},"risk_flags":[]}],"coverage_gap":false,"conflicts":[]}
```

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/api tests/integration/api -v`

Expected: API route and contract tests pass.

```bash
git add src/skillforge_kb/api tests/unit/api tests/integration/api tests/fixtures/contracts
git commit -m "feat: expose versioned evidence API"
```

---

### Task 10: Build the offline retrieval benchmark and metric runner

**Files:**
- Create: `src/skillforge_kb/evaluation/__init__.py`
- Create: `src/skillforge_kb/evaluation/dataset.py`
- Create: `src/skillforge_kb/evaluation/metrics.py`
- Create: `src/skillforge_kb/evaluation/runner.py`
- Create: `resources/evaluation/retrieval_v1.jsonl`
- Test: `tests/unit/evaluation/test_dataset.py`
- Test: `tests/unit/evaluation/test_metrics.py`

**Interfaces:**
- Consumes: `EvidenceService` and labeled JSONL rows.
- Produces: `EvaluationReport` containing global, language, module, type, parity, latency, and citation metrics.

- [ ] **Step 1: Define one complete benchmark row and validation tests**

```json
{"query_id":"tr-en-001","query":"What does the scaling factor sqrt(d_k) prevent in dot-product attention?","language":"en","module":"transformer","question_type":"derivation","difficulty":3,"relevant_concept_ids":["dl.transformer.self-attention"],"required_chunk_ids":["attention-paper-p4-scaling"],"acceptable_chunk_ids":["d2l-attention-scoring"],"irrelevant_chunk_ids":["logistic-regression-loss"]}
```

Tests must reject duplicate query IDs, empty required/acceptable sets, unknown concepts, unsupported language/module/type, and benchmark files below the configured minimum count.

Use this validated dataset loader:

```python
# src/skillforge_kb/evaluation/dataset.py
import json
from pathlib import Path

from pydantic import BaseModel, Field

from skillforge_kb.domain.enums import Language
from skillforge_kb.ontology.catalog import OntologyCatalog


class BenchmarkRow(BaseModel):
    query_id: str
    query: str = Field(min_length=2)
    language: Language
    module: str
    question_type: str
    difficulty: int = Field(ge=1, le=4)
    relevant_concept_ids: list[str] = Field(min_length=1)
    required_chunk_ids: list[str] = Field(min_length=1)
    acceptable_chunk_ids: list[str] = Field(default_factory=list)
    irrelevant_chunk_ids: list[str] = Field(default_factory=list)


def load_benchmark(
    path: Path,
    catalog: OntologyCatalog,
    min_count: int = 150,
) -> list[BenchmarkRow]:
    rows = [BenchmarkRow.model_validate(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) < min_count:
        raise ValueError(f"benchmark requires at least {min_count} rows")
    ids = [row.query_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate query IDs")
    for row in rows:
        unknown = set(row.relevant_concept_ids) - set(catalog.concepts)
        if unknown:
            raise ValueError(f"unknown benchmark concepts: {sorted(unknown)}")
        if not (row.required_chunk_ids or row.acceptable_chunk_ids):
            raise ValueError(f"query has no relevant evidence: {row.query_id}")
    return rows
```

- [ ] **Step 2: Implement metrics with hand-calculated fixtures**

Implement the metric functions directly, without external metric packages:

```python
# src/skillforge_kb/evaluation/metrics.py
import math


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        raise ValueError("relevant set cannot be empty")
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str], k: int) -> float:
    for rank, chunk_id in enumerate(ranked[:k], start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def dcg_at_k(ranked: list[str], relevance: dict[str, int], k: int) -> float:
    return sum(
        (2 ** relevance.get(chunk_id, 0) - 1) / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked[:k], start=1)
    )


def ndcg_at_k(ranked: list[str], relevance: dict[str, int], k: int) -> float:
    ideal = sorted(relevance, key=lambda chunk_id: (-relevance[chunk_id], chunk_id))
    denominator = dcg_at_k(ideal, relevance, k)
    return 0.0 if denominator == 0 else dcg_at_k(ranked, relevance, k) / denominator


def language_parity_gap(chinese_score: float, english_score: float) -> float:
    return abs(chinese_score - english_score)


def citation_relocalization_rate(relocalized: int, checked: int) -> float:
    if checked <= 0:
        raise ValueError("checked citations must be positive")
    return relocalized / checked


def percentile_latency(samples_ms: list[float], percentile: float) -> float:
    if not samples_ms:
        raise ValueError("latency samples cannot be empty")
    ordered = sorted(samples_ms)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]
```

Unit tests use ranked list `["a", "x", "b"]`, relevant set `{"a", "b"}`, and graded relevance `{"a": 2, "b": 1}`. Assert Recall@2 = 0.5, reciprocal rank = 1.0, nDCG values to four decimal places, parity gap = 0.04, and P95 of 20 ordered samples equals the nineteenth sample.

- [ ] **Step 3: Implement the ablation matrix**

Run these configurations from one immutable benchmark and one indexed corpus version:

1. `bm25_only`;
2. `dense_only`;
3. `bm25_dense`;
4. `hybrid_graph`;
5. `hybrid_graph_rerank`.

Write JSON and Markdown reports with configuration, source manifest hash, ontology version, collection version, metric groups, failures, and latency samples.

Define the matrix as immutable configuration data consumed by `runner.py`:

```python
# src/skillforge_kb/evaluation/runner.py
from dataclasses import dataclass


@dataclass(frozen=True)
class AblationConfig:
    name: str
    sparse: bool
    dense: bool
    graph: bool
    rerank: bool


ABLATIONS = (
    AblationConfig("bm25_only", True, False, False, False),
    AblationConfig("dense_only", False, True, False, False),
    AblationConfig("bm25_dense", True, True, False, False),
    AblationConfig("hybrid_graph", True, True, True, False),
    AblationConfig("hybrid_graph_rerank", True, True, True, True),
)
```

- [ ] **Step 4: Add the acceptance gate**

Create one report model with an aggregate failure message:

```python
# append to src/skillforge_kb/evaluation/runner.py
from pydantic import BaseModel


class EvaluationReport(BaseModel):
    recall_at_5: float
    mrr_at_10: float
    ndcg_at_10: float
    concept_coverage: float
    language_parity_gap: float
    citation_relocalization: float
    duplicate_rate: float
    p95_latency_seconds: float

    def assert_v1_acceptance(self) -> None:
        checks = {
            "Recall@5 >= 0.85": self.recall_at_5 >= 0.85,
            "MRR@10 >= 0.75": self.mrr_at_10 >= 0.75,
            "nDCG@10 >= 0.80": self.ndcg_at_10 >= 0.80,
            "concept coverage >= 0.90": self.concept_coverage >= 0.90,
            "language parity gap <= 0.05": self.language_parity_gap <= 0.05,
            "citation relocalization >= 0.98": self.citation_relocalization >= 0.98,
            "duplicate rate < 0.02": self.duplicate_rate < 0.02,
            "P95 latency < 2 seconds": self.p95_latency_seconds < 2.0,
        }
        failures = [label for label, passed in checks.items() if not passed]
        if failures:
            raise AssertionError("v1 acceptance failed: " + "; ".join(failures))
```

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest tests/unit/evaluation -v`

Expected: dataset validation, metric math, ablation configuration, and aggregate acceptance tests pass.

```bash
git add src/skillforge_kb/evaluation resources/evaluation tests/unit/evaluation
git commit -m "feat: evaluate retrieval quality and ablations"
```

---

### Task 11: Add curation, build, review, and reporting CLI workflows

**Files:**
- Create: `src/skillforge_kb/cli.py`
- Create: `resources/sources/manifest.yaml`
- Create: `docs/knowledge-base/source-policy.md`
- Create: `docs/knowledge-base/curation-guide.md`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: governance, ingestion, ontology, storage, indexing, and evaluation services from Tasks 2–10.
- Produces: repeatable operator commands and machine-readable build/review reports.

- [ ] **Step 1: Write failing CLI help and dry-run tests**

Use Typer's `CliRunner` to assert these commands exist and return exit 0 for `--help`: `source validate`, `source register`, `build dry-run`, `build publish`, `review batch`, `evaluate run`, and `report corpus`.

- [ ] **Step 2: Implement `source validate` and `build dry-run` first**

`source validate` must parse the YAML manifest through `SourceRecord`, verify unique IDs, HTTPS URLs, license rules, language, tier, and duplicate canonical URLs. `build dry-run` must fetch and parse but perform no PostgreSQL, Qdrant, or Neo4j writes; it outputs source counts, extraction failures, candidate chunks, exact duplicates, near duplicates, and unknown concept IDs.

- [ ] **Step 3: Implement resumable publication batches**

`build publish --batch-size 25 --run-id <id>` must persist each source's stage and counts. Re-running the same run ID skips successful source stages and retries failed stages. Publication order is PostgreSQL chunk transaction, Qdrant upsert, then Neo4j relationship publication; a failed later adapter leaves the run incomplete and safe to resume.

- [ ] **Step 4: Implement human review batches**

`review batch --limit 25 --language zh|en --module <module>` must export a review CSV containing chunk ID, source, locator, text, concepts, language, difficulty, tier, and reviewer columns. `review import <csv>` must require reviewer name, decision, terminology decision, and optional rejection reason before changing a chunk to `HUMAN_REVIEWED`.

- [ ] **Step 5: Curate the source manifest by exact admission rules**

For each deep module, register at least two independent S1 source families and two S2 teaching source families. For every core concept, ensure at least one Chinese and one English evidence source or a reviewed `derived` Chinese explanation linked to an English S1 source. Record license URL and allowed use for every full-text source. Any source without completed license review remains `pending` and cannot publish.

- [ ] **Step 6: Scale in reviewable batches until corpus gates pass**

Publish and review batches of 25 chunks. Run `report corpus` after each source family. Stop adding themes on 2026-08-07. The corpus gate passes only when the report confirms 120–180 concepts, 800–1,200 total reviewed chunks, 60–90 examples/exercises, >=90% core-concept bilingual coverage, 100% provenance/license registration, and <2% near duplicates.

- [ ] **Step 7: Verify CLI tests and commit**

Run: `uv run pytest tests/unit/test_cli.py -v`

Expected: help, validation, dry-run, resume, review-import, and report-gate tests pass.

```bash
git add src/skillforge_kb/cli.py resources/sources docs/knowledge-base tests/unit/test_cli.py
git commit -m "feat: operationalize governed corpus curation"
```

---

### Task 12: Run end-to-end acceptance, harden operations, and freeze KB v1

**Files:**
- Create: `tests/integration/test_end_to_end.py`
- Create: `tests/performance/test_retrieval_latency.py`
- Create: `docs/knowledge-base/operations.md`
- Create: `docs/knowledge-base/evidence-api.md`
- Create: `docs/knowledge-base/evaluation.md`
- Create: `docs/knowledge-base/rebuild.md`
- Create: `README.md`

**Interfaces:**
- Consumes: every prior task.
- Produces: a frozen `kb-v1` corpus/index/API release that the separate LangGraph plan can consume.

- [ ] **Step 1: Write the failing end-to-end scenario**

The test starts with one admitted HTML source and one admitted PDF source, runs migration, parse, normalization, chunking, concept mapping, human-review fixture import, PostgreSQL publication, Qdrant indexing, Neo4j publication, and an API query. Assert that the final evidence hit contains the original source URL, locator, concept ID, language, channel scores, final score, and no unreviewed chunks.

- [ ] **Step 2: Add failure-path scenarios**

Test no-result coverage gap, Neo4j outage degradation, Qdrant outage 503, invalid license rejection, stale-version preference, conflicting evidence flags, idempotent rebuild, and resume after an interrupted Qdrant publication.

- [ ] **Step 3: Add P95 performance measurement**

Warm the service with 20 unmeasured queries, then run the 150+ benchmark queries three times on the release corpus. Calculate P50, P95, and maximum latency. Fail when P95 exceeds 2 seconds on the documented reference machine; record CPU, RAM, model, Qdrant version, Neo4j version, and corpus version in the report.

- [ ] **Step 4: Run the full quality gate**

Run: `uv run ruff check src tests`

Expected: `All checks passed!`

Run: `uv run mypy src`

Expected: `Success: no issues found`.

Run: `uv run pytest tests/unit -v`

Expected: all unit tests pass without Docker.

Run: `docker compose up -d`

Expected: PostgreSQL healthy; Qdrant and Neo4j reachable.

Run: `uv run pytest tests/integration tests/performance -v -m integration`

Expected: all integration, failure-path, contract, and latency tests pass.

Run: `uv run skillforge-kb evaluate run --config hybrid_graph_rerank --assert-v1`

Expected: exit 0 with every v1 metric at or above its acceptance threshold.

- [ ] **Step 5: Write operator and consumer documentation**

Document installation, environment variables, service startup, migration, source registration, dry run, batch publication, human review, rebuild, rollback, benchmark execution, report interpretation, API examples, schema versioning, outage behavior, and the rule that agents use Evidence API only.

- [ ] **Step 6: Create and verify the release tag**

```bash
git add README.md docs/knowledge-base tests/integration/test_end_to_end.py tests/performance/test_retrieval_latency.py
git commit -m "release: freeze AI learning knowledge base v1"
git tag -a kb-v1 -m "AI learning knowledge base v1"
```

Run: `git status --short`

Expected: no tracked changes. Existing competition PDFs, images, and personal materials may remain untracked until a separate data-governance decision is made.

Run: `git show --stat --oneline kb-v1`

Expected: the release commit and knowledge-base documentation are shown.

---

## Spec Coverage Matrix

| Approved design requirement | Implemented by |
| --- | --- |
| Stable domain and Evidence Package contracts | Tasks 1, 8, 9 |
| Source provenance, license, lifecycle, and human review | Tasks 2, 3, 4, 11 |
| Reproducible acquisition, parsing, normalization, deduplication, and chunking | Tasks 4, 5, 11 |
| Bilingual concept IDs, aliases, prerequisites, and bounded graph expansion | Task 6 |
| PostgreSQL, Qdrant dense/sparse retrieval, and Neo4j responsibilities | Tasks 3, 6, 7 |
| Three-channel retrieval, fusion, scoring, traceability, and degradation | Task 8 |
| Versioned Evidence API boundary for future LangGraph agents | Task 9 |
| 150+ query benchmark, required metrics, ablations, and acceptance thresholds | Tasks 10, 12 |
| 120–180 concepts, 800–1,200 chunks, 60–90 examples/exercises, bilingual coverage | Task 11 |
| Fault handling, resumability, performance, rebuild, and operations | Tasks 8, 9, 11, 12 |
| 2 + 2 + 2 ownership and cross-pair review | Execution Order and Ownership |
| Agent logic excluded from this implementation scope | Global Constraints and Separate Follow-on Plans |

No approved knowledge-base requirement is deferred to an unspecified task. Agent-internal logic is intentionally outside this subproject and is named as a separate follow-on plan.

## Execution Order and Ownership

| Task | Primary pair | Required review |
| --- | --- | --- |
| 1–3 Domain, governance, infrastructure | Knowledge-base pair | Agent pair reviews API-facing contracts |
| 4–7 ingestion, ontology, indexes | Knowledge-base pair | Algorithm pair reviews data and retrieval assumptions |
| 8 retrieval service | Knowledge-base pair + algorithm pair | Both pairs approve scoring and fallback behavior |
| 9 Evidence API | Knowledge-base pair | Agent pair runs consumer contract review |
| 10 benchmark and ablations | Algorithm pair | Knowledge-base pair verifies corpus/index versioning |
| 11 corpus curation and scale | Knowledge-base pair + support reviewers | Algorithm pair audits benchmark leakage |
| 12 acceptance and freeze | All three technical pairs | Project lead signs release gate |

Tasks 1–3 are sequential. After Task 3, Tasks 4 and 6 can proceed in parallel. Task 7 depends on Task 5; Task 8 depends on Tasks 6 and 7; Task 9 depends on Task 8. Task 10 can start after Task 8 with a pilot dataset and must finish after Task 11 reaches release scale. Task 12 is the final gate.

## Separate Follow-on Plans

After `kb-v1` is tagged, create independent plans for:

1. LangGraph agent skeleton and Evidence API integration;
2. algorithm selection, prototypes, baselines, and agent-internal integration;
3. frontend visualization, 60-case system evaluation, and competition delivery package.

These follow-on plans must pin Evidence API schema version 1.0 and must not bypass the knowledge-base service boundary.
