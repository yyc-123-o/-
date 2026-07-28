from typing import Protocol

from .models import EvidenceChunk, SourceRecord


class ConceptGraph(Protocol):
    def prerequisites(self, concept_id: str, max_depth: int = 2) -> list[str]: ...


class SourceRepository(Protocol):
    def get(self, source_id: str) -> SourceRecord | None: ...

    def save(self, source: SourceRecord) -> None: ...

    def list_all(self) -> list[SourceRecord]: ...


class ChunkRepository(Protocol):
    def save_many(self, chunks: list[EvidenceChunk]) -> None: ...

    def get_many(self, chunk_ids: list[str]) -> list[EvidenceChunk]: ...
