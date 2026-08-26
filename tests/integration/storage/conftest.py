from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

psycopg = pytest.importorskip(
    "psycopg",
    reason="PostgreSQL integration tests require psycopg",
)

from skillforge_kb.domain.enums import Language, LicenseStatus, SourceTier
from skillforge_kb.domain.models import SourceRecord


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        dsn = container.get_connection_url().replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        yield dsn


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
