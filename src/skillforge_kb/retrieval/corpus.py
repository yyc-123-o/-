import json
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import KnowledgeChunk


class KnowledgeCorpus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunks: tuple[KnowledgeChunk, ...] = ()
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "KnowledgeCorpus":
        ids = [chunk.chunk_id for chunk in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chunk_id")
        return self

    @classmethod
    def load(cls, path: Path) -> "KnowledgeCorpus":
        chunks: list[KnowledgeChunk] = []
        seen_ids: set[str] = set()
        cls._append_file(path, chunks, seen_ids)
        return cls(chunks=tuple(chunks), digest=build_corpus_digest(tuple(chunks)))

    @classmethod
    def load_many(cls, paths: tuple[Path, ...]) -> "KnowledgeCorpus":
        if not paths:
            raise ValueError("knowledge corpus requires at least one file")
        chunks: list[KnowledgeChunk] = []
        seen_ids: set[str] = set()
        for path in paths:
            cls._append_file(path, chunks, seen_ids)
        frozen_chunks = tuple(chunks)
        return cls(chunks=frozen_chunks, digest=build_corpus_digest(frozen_chunks))

    @staticmethod
    def _append_file(
        path: Path,
        chunks: list[KnowledgeChunk],
        seen_ids: set[str],
    ) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"knowledge corpus file unavailable: {path}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                chunk = KnowledgeChunk.model_validate(raw)
            except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
                raise ValueError(
                    f"invalid knowledge chunk at {path} line {line_number}: {exc}"
                ) from exc
            if chunk.chunk_id in seen_ids:
                raise ValueError(
                    f"duplicate chunk_id at {path} line {line_number}: {chunk.chunk_id}"
                )
            seen_ids.add(chunk.chunk_id)
            chunks.append(chunk)


def build_corpus_digest(chunks: tuple[KnowledgeChunk, ...]) -> str:
    canonical = json.dumps(
        [chunk.model_dump(mode="json") for chunk in chunks],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
