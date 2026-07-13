from datetime import UTC, datetime

import psycopg
import pytest

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus, SourceTier
from skillforge_kb.domain.models import Citation, EvidenceChunk, SourceRecord
from skillforge_kb.storage.postgres import (
    PostgresChunkRepository,
    PostgresSourceRepository,
    apply_migrations,
)

_TESTCONTAINERS_DEPRECATION = (
    "ignore:The @wait_container_is_ready decorator is deprecated and will be removed "
    "in a future version\\.:DeprecationWarning:"
)
pytestmark = [
    pytest.mark.filterwarnings(
        _TESTCONTAINERS_DEPRECATION + r"testcontainers\.core\.waiting_utils"
    ),
    pytest.mark.filterwarnings(_TESTCONTAINERS_DEPRECATION + r"testcontainers\.postgres"),
]


@pytest.mark.integration
def test_migrations_are_idempotent(postgres_connection: psycopg.Connection) -> None:
    apply_migrations(postgres_connection)
    apply_migrations(postgres_connection)

    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        assert cursor.fetchall() == [("001_initial",)]


@pytest.mark.integration
def test_postgres_source_round_trip(
    postgres_connection: psycopg.Connection, sample_source: SourceRecord
) -> None:
    apply_migrations(postgres_connection)
    repository = PostgresSourceRepository(postgres_connection)
    repository.save(sample_source)
    assert repository.get(sample_source.source_id) == sample_source


@pytest.mark.integration
def test_source_repository_upserts_and_lists_in_source_id_order(
    postgres_connection: psycopg.Connection, sample_source: SourceRecord
) -> None:
    apply_migrations(postgres_connection)
    repository = PostgresSourceRepository(postgres_connection)
    later_source = sample_source.model_copy(
        update={"source_id": "z-source", "title": "Later source"}
    )
    earlier_source = SourceRecord(
        source_id="a-source",
        title="Earlier source",
        canonical_url="https://example.edu/earlier",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=LicenseStatus.ALLOWED,
        license_url="https://example.edu/license",
        retrieved_at=datetime.now(UTC),
    )

    repository.save(later_source)
    repository.save(earlier_source)
    updated_source = later_source.model_copy(update={"title": "Updated later source"})
    repository.save(updated_source)

    assert repository.get(later_source.source_id) == updated_source
    assert repository.get("missing-source") is None
    source_ids = [source.source_id for source in repository.list_all()]
    assert {earlier_source.source_id, later_source.source_id}.issubset(source_ids)
    assert source_ids == sorted(source_ids)


@pytest.mark.integration
def test_chunk_repository_upserts_and_returns_requested_existing_ids_in_order(
    postgres_connection: psycopg.Connection, sample_source: SourceRecord
) -> None:
    apply_migrations(postgres_connection)
    PostgresSourceRepository(postgres_connection).save(sample_source)
    repository = PostgresChunkRepository(postgres_connection)
    first_chunk = _chunk("chunk-first", sample_source.source_id, "a" * 64)
    second_chunk = _chunk("chunk-second", sample_source.source_id, "b" * 64)

    repository.save_many([first_chunk, second_chunk])

    assert repository.get_many([second_chunk.chunk_id, "missing-chunk", first_chunk.chunk_id]) == [
        second_chunk,
        first_chunk,
    ]
    assert repository.get_many([]) == []

    updated_chunk = first_chunk.model_copy(
        update={
            "text": "Updated evidence text that remains long enough for validation.",
            "content_hash": "c" * 64,
            "reviewed": True,
        }
    )
    repository.save_many([updated_chunk])

    assert repository.get_many([first_chunk.chunk_id]) == [updated_chunk]


def _chunk(chunk_id: str, source_id: str, content_hash: str) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        concept_ids=["ml.supervised.logistic-regression"],
        language=Language.EN,
        content_kind=ContentKind.DEFINITION,
        text="Logistic regression models conditional probability with a sigmoid function.",
        citation=Citation(
            url="https://example.edu/source",
            locator=f"section-{chunk_id}",
            title="Sample open source",
        ),
        content_hash=content_hash,
    )
