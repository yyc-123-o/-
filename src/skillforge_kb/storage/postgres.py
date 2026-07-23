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
                (
                    source.source_id,
                    Jsonb(source.model_dump(mode="json")),
                    source.review_status.value,
                ),
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
                for chunk in (
                    EvidenceChunk.model_validate(row["payload"]) for row in cursor.fetchall()
                )
            }
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]
