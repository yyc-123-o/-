# Knowledge Base Fusion Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only fusion intake pipeline that inventories both teammate knowledge bases and assigns a deterministic outcome to all 2,133 JSONL records without publishing or mutating source data.

**Architecture:** Add a focused `skillforge_kb.fusion` package with stable intake models, one adapter per teammate dataset, and an orchestrator that writes atomic JSONL/JSON reports. The first phase produces candidate and rejection metadata only; PostgreSQL, Qdrant, Neo4j, legacy pickle, and legacy FAISS files remain untouched.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, pytest, existing normalization helpers, Ruff, mypy.

## Global Constraints

- Execute code in the existing `D:\张维揭榜挂帅\.worktrees\kb-v1` worktree on branch `feature/kb-v1`.
- Preserve the existing uncommitted changes in `src/skillforge_kb/storage/postgres.py`, `tests/integration/storage/conftest.py`, and `tests/integration/storage/test_postgres.py`.
- Treat `D:\张维揭榜挂帅\知识库` and `D:\张维揭榜挂帅\processed` as read-only inputs.
- Never unpickle `index_bm25.pkl` or `index_chunks.pkl`; do not load the legacy FAISS index into the application.
- Do not publish candidates or alter PostgreSQL, Qdrant, or Neo4j in this phase.
- Every input JSONL line must receive exactly one of `accepted`, `rejected`, `superseded`, or `reference_only`.
- `accepted` means accepted into the candidate layer, not approved for publication; every phase-one outcome has `publishable=false`.
- Write generated reports only under the caller-provided output directory; use `reports/generated/fusion-v1` for the real run.
- Output files must be deterministic and atomically replaced so a failed run cannot leave a partially written report.
- Follow TDD for each task and commit only the files listed in that task.

---

### Task 1: Define Fusion Contracts and Deterministic Input Inventory

**Files:**
- Create: `src/skillforge_kb/fusion/__init__.py`
- Create: `src/skillforge_kb/fusion/models.py`
- Create: `src/skillforge_kb/fusion/inventory.py`
- Test: `tests/unit/fusion/test_inventory.py`

**Interfaces:**
- Consumes: `skillforge_kb.domain.enums.Language`.
- Produces: `InputDataset`, `CorpusId`, `FusionDisposition`, `ReasonCode`, `FileInventoryEntry`, `SourceCandidate`, `ChunkCandidate`, `FusionOutcome`, `DryRunSummary`, `sha256_file(path)`, and `inventory_tree(root)`.

- [ ] **Step 1: Write failing inventory and model tests**

Create `tests/unit/fusion/test_inventory.py`:

```python
from pathlib import Path

from skillforge_kb.fusion.inventory import inventory_tree, sha256_file
from skillforge_kb.fusion.models import (
    CorpusId,
    FusionDisposition,
    FusionOutcome,
    InputDataset,
    ReasonCode,
)


def test_inventory_tree_is_sorted_and_hashes_file_bytes(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "z.txt").write_bytes(b"z")
    (tmp_path / "nested" / "a.txt").write_bytes(b"alpha")

    entries = inventory_tree(tmp_path)

    assert [entry.relative_path for entry in entries] == ["nested/a.txt", "z.txt"]
    assert entries[0].size_bytes == 5
    assert entries[0].sha256 == sha256_file(tmp_path / "nested" / "a.txt")
    assert all(entry.root == str(tmp_path.resolve()) for entry in entries)


def test_fusion_outcome_defaults_to_non_publishable() -> None:
    outcome = FusionOutcome(
        input_dataset=InputDataset.PILOT,
        input_line=7,
        raw_line_sha256="a" * 64,
        disposition=FusionDisposition.ACCEPTED,
        corpus_id=CorpusId.LEARNING_EVIDENCE,
        reason_codes=[ReasonCode.HUMAN_REVIEW_REQUIRED],
    )

    assert outcome.publishable is False
    assert outcome.candidate is None
```

- [ ] **Step 2: Run the tests and confirm missing-module failure**

Run:

```powershell
uv run pytest tests/unit/fusion/test_inventory.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'skillforge_kb.fusion'`.

- [ ] **Step 3: Implement fusion models**

Create `src/skillforge_kb/fusion/__init__.py`:

```python
"""Read-only intake and reconciliation for teammate knowledge bases."""
```

Create `src/skillforge_kb/fusion/models.py`:

```python
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from skillforge_kb.domain.enums import Language


class InputDataset(StrEnum):
    PILOT = "pilot"
    LEGACY_INDEX = "legacy_index"


class CorpusId(StrEnum):
    LEARNING_EVIDENCE = "learning_evidence"
    AGENT_ENGINEERING = "agent_engineering"
    PROJECT_MATERIAL = "project_material"


class FusionDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    REFERENCE_ONLY = "reference_only"


class ReasonCode(StrEnum):
    INVALID_JSON = "invalid_json"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MISSING_SOURCE_PATH = "missing_source_path"
    LICENSE_REVIEW_REQUIRED = "license_review_required"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    AUTOMATED_LABEL_REVIEW_REQUIRED = "automated_label_review_required"
    NORMALIZED_HASH_MISMATCH = "normalized_hash_mismatch"
    ENGLISH_WORD_CONCATENATION = "english_word_concatenation"
    MISSING_PROVENANCE = "missing_provenance"
    TOKEN_COUNT_IS_CHARACTER_COUNT = "token_count_is_character_count"
    TEXT_TOO_SHORT = "text_too_short"
    TEXT_REQUIRES_RECHUNKING = "text_requires_rechunking"
    EXACT_DUPLICATE = "exact_duplicate"
    OVERLAPS_AUTHORITATIVE_SOURCE = "overlaps_authoritative_source"


class FileInventoryEntry(BaseModel):
    root: str
    relative_path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceCandidate(BaseModel):
    source_key: str
    source_id: str
    title: str
    corpus_id: CorpusId
    canonical_url: str | None = None
    source_path: str | None = None
    license_label: str | None = None
    provenance_complete: bool = False
    input_dataset: InputDataset
    input_line: int = Field(ge=1)


class ChunkCandidate(BaseModel):
    chunk_id: str
    source: SourceCandidate
    language: Language | None = None
    text: str
    locator: str | None = None
    citation_url: str | None = None
    concept_ids: list[str] = Field(default_factory=list)
    content_kind: str | None = None
    difficulty: int | None = None
    normalized_hash: str
    original_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusionOutcome(BaseModel):
    input_dataset: InputDataset
    input_line: int = Field(ge=1)
    raw_line_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: FusionDisposition
    corpus_id: CorpusId | None = None
    publishable: bool = False
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    candidate: ChunkCandidate | None = None
    error: str | None = None


class DryRunSummary(BaseModel):
    input_rows: int = Field(ge=0)
    source_count: int = Field(ge=0)
    input_file_count: int = Field(ge=0)
    outcome_counts: dict[str, int]
    reason_counts: dict[str, int]
    corpus_counts: dict[str, int]
```

- [ ] **Step 4: Implement deterministic file inventory**

Create `src/skillforge_kb/fusion/inventory.py`:

```python
from hashlib import sha256
from pathlib import Path

from .models import FileInventoryEntry


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def inventory_tree(root: Path) -> list[FileInventoryEntry]:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"input root is not a directory: {resolved}")
    files = sorted(
        (path for path in resolved.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(resolved).as_posix(),
    )
    return [
        FileInventoryEntry(
            root=str(resolved),
            relative_path=path.relative_to(resolved).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for path in files
    ]
```

- [ ] **Step 5: Run focused quality checks**

Run:

```powershell
uv run pytest tests/unit/fusion/test_inventory.py -v
uv run ruff check src/skillforge_kb/fusion tests/unit/fusion/test_inventory.py
uv run mypy src/skillforge_kb/fusion
```

Expected: all commands exit 0; pytest reports 2 passed.

- [ ] **Step 6: Commit the fusion contracts**

```powershell
git add src/skillforge_kb/fusion tests/unit/fusion/test_inventory.py
git commit -m "feat: define fusion intake contracts"
```

---

### Task 2: Adapt the Provenance-Rich Pilot Dataset

**Files:**
- Create: `src/skillforge_kb/fusion/jsonl.py`
- Create: `src/skillforge_kb/fusion/pilot.py`
- Test: `tests/unit/fusion/test_pilot.py`

**Interfaces:**
- Consumes: `FusionOutcome`, `ReasonCode`, `SourceCandidate`, `ChunkCandidate`, `sha256_text`, a pilot JSONL path, and the workspace root used to resolve `source_path`.
- Produces: `JsonlRecord`, `iter_jsonl(path)`, `has_english_word_concatenation(text)`, and `adapt_pilot(path, workspace_root) -> list[FusionOutcome]`.

- [ ] **Step 1: Write failing pilot adapter tests**

Create `tests/unit/fusion/test_pilot.py`:

```python
import json
from hashlib import sha256
from pathlib import Path

from skillforge_kb.fusion.models import FusionDisposition, ReasonCode
from skillforge_kb.fusion.pilot import adapt_pilot, has_english_word_concatenation
from skillforge_kb.ingestion.normalize import sha256_text


def _write_pilot(path: Path, source_path: str, text: str, content_hash: str) -> None:
    row = {
        "chunk_id": "paper_attention_chunk_1",
        "source_id": "paper_attention_2017",
        "source_title": "Attention Is All You Need",
        "source_path": source_path,
        "source_url": "https://arxiv.org/abs/1706.03762",
        "tier": "S1",
        "license_status": "allowed",
        "license": "arXiv",
        "language": "en",
        "module": "transformer",
        "content_kind": "definition",
        "concept_ids": ["llm.transformer.attention"],
        "difficulty": 3,
        "locator": "page 1",
        "text": text,
        "content_hash": content_hash,
        "review_status": "candidate",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def test_pilot_adapter_accepts_structural_candidate_and_preserves_citation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source bytes")
    text = "Self-attention relates every sequence position to every other position."
    input_path = tmp_path / "pilot.jsonl"
    _write_pilot(input_path, "source.pdf", text, sha256_text(text))

    outcome = adapt_pilot(input_path, tmp_path)[0]

    assert outcome.disposition is FusionDisposition.ACCEPTED
    assert outcome.publishable is False
    assert outcome.candidate is not None
    assert outcome.candidate.citation_url == "https://arxiv.org/abs/1706.03762"
    assert outcome.candidate.locator == "page 1"
    assert ReasonCode.LICENSE_REVIEW_REQUIRED in outcome.reason_codes
    assert ReasonCode.HUMAN_REVIEW_REQUIRED in outcome.reason_codes


def test_pilot_adapter_supersedes_concatenated_english_and_flags_hash_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source bytes")
    text = "Weproposeanewarchitecturebasedsolelyonattentionmechanismswithoutrecurrence."
    input_path = tmp_path / "pilot.jsonl"
    stored_text = text + "  "
    raw_hash = sha256(stored_text.encode("utf-8")).hexdigest()
    _write_pilot(input_path, "source.pdf", stored_text, raw_hash)

    outcome = adapt_pilot(input_path, tmp_path)[0]

    assert outcome.disposition is FusionDisposition.SUPERSEDED
    assert ReasonCode.ENGLISH_WORD_CONCATENATION in outcome.reason_codes
    assert ReasonCode.NORMALIZED_HASH_MISMATCH in outcome.reason_codes
    assert has_english_word_concatenation(text)


def test_pilot_adapter_rejects_invalid_json_without_dropping_line(tmp_path: Path) -> None:
    input_path = tmp_path / "pilot.jsonl"
    input_path.write_text("{not-json}\n", encoding="utf-8")

    outcome = adapt_pilot(input_path, tmp_path)[0]

    assert outcome.input_line == 1
    assert outcome.disposition is FusionDisposition.REJECTED
    assert outcome.reason_codes == [ReasonCode.INVALID_JSON]
    assert outcome.candidate is None
```

- [ ] **Step 2: Run pilot tests and confirm import failure**

Run:

```powershell
uv run pytest tests/unit/fusion/test_pilot.py -v
```

Expected: collection fails because `skillforge_kb.fusion.pilot` does not exist.

- [ ] **Step 3: Implement lossless JSONL iteration**

Create `src/skillforge_kb/fusion/jsonl.py`:

```python
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonlRecord:
    line_number: int
    raw: str
    value: dict[str, Any] | None
    error: str | None


def iter_jsonl(path: Path) -> Iterator[JsonlRecord]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            value_text = raw.rstrip("\r\n")
            try:
                value = json.loads(value_text)
                if not isinstance(value, dict):
                    raise ValueError("JSONL value must be an object")
            except (json.JSONDecodeError, ValueError) as exc:
                yield JsonlRecord(line_number, value_text, None, str(exc))
            else:
                yield JsonlRecord(line_number, value_text, value, None)
```

- [ ] **Step 4: Implement the pilot adapter**

Create `src/skillforge_kb/fusion/pilot.py`:

```python
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from skillforge_kb.domain.enums import Language
from skillforge_kb.ingestion.normalize import sha256_text

from .jsonl import JsonlRecord, iter_jsonl
from .models import (
    ChunkCandidate,
    CorpusId,
    FusionDisposition,
    FusionOutcome,
    InputDataset,
    ReasonCode,
    SourceCandidate,
)

LONG_ALPHA_RUN = re.compile(r"[A-Za-z]{40,}")


def _raw_hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def has_english_word_concatenation(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    long_words = [word for word in words if len(word) >= 25]
    alpha_characters = sum(map(len, words))
    long_characters = sum(map(len, long_words))
    return bool(long_words) and (
        LONG_ALPHA_RUN.search(text) is not None
        or long_characters / max(alpha_characters, 1) >= 0.12
    )


def _invalid(record: JsonlRecord) -> FusionOutcome:
    return FusionOutcome(
        input_dataset=InputDataset.PILOT,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=FusionDisposition.REJECTED,
        reason_codes=[ReasonCode.INVALID_JSON],
        error=record.error,
    )


def _adapt_record(record: JsonlRecord, workspace_root: Path) -> FusionOutcome:
    if record.value is None:
        return _invalid(record)
    row: dict[str, Any] = record.value
    required = (
        "chunk_id",
        "source_id",
        "source_title",
        "source_path",
        "source_url",
        "language",
        "text",
        "content_hash",
        "locator",
    )
    missing = [field for field in required if not row.get(field)]
    if missing:
        return FusionOutcome(
            input_dataset=InputDataset.PILOT,
            input_line=record.line_number,
            raw_line_sha256=_raw_hash(record.raw),
            disposition=FusionDisposition.REJECTED,
            reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
            error=f"missing required fields: {', '.join(missing)}",
        )

    text = str(row["text"])
    language = Language(str(row["language"]))
    source_path = str(row["source_path"])
    resolved_source = workspace_root / Path(source_path.replace("/", "\\"))
    reasons = [
        ReasonCode.LICENSE_REVIEW_REQUIRED,
        ReasonCode.HUMAN_REVIEW_REQUIRED,
        ReasonCode.AUTOMATED_LABEL_REVIEW_REQUIRED,
    ]
    disposition = FusionDisposition.ACCEPTED
    if not resolved_source.exists():
        reasons.append(ReasonCode.MISSING_SOURCE_PATH)
        disposition = FusionDisposition.REFERENCE_ONLY
    normalized_hash = sha256_text(text)
    if normalized_hash != str(row["content_hash"]):
        reasons.append(ReasonCode.NORMALIZED_HASH_MISMATCH)
    if language is Language.EN and has_english_word_concatenation(text):
        reasons.append(ReasonCode.ENGLISH_WORD_CONCATENATION)
        disposition = FusionDisposition.SUPERSEDED

    source = SourceCandidate(
        source_key=f"source:{row['source_id']}",
        source_id=str(row["source_id"]),
        title=str(row["source_title"]),
        corpus_id=CorpusId.LEARNING_EVIDENCE,
        canonical_url=str(row["source_url"]),
        source_path=source_path,
        license_label=str(row.get("license") or "") or None,
        provenance_complete=True,
        input_dataset=InputDataset.PILOT,
        input_line=record.line_number,
    )
    candidate = ChunkCandidate(
        chunk_id=str(row["chunk_id"]),
        source=source,
        language=language,
        text=text,
        locator=str(row["locator"]),
        citation_url=str(row["source_url"]),
        concept_ids=[str(value) for value in row.get("concept_ids", [])],
        content_kind=str(row.get("content_kind") or "") or None,
        difficulty=int(row["difficulty"]) if row.get("difficulty") is not None else None,
        normalized_hash=normalized_hash,
        original_hash=str(row["content_hash"]),
        metadata={"review_status": row.get("review_status"), "module": row.get("module")},
    )
    return FusionOutcome(
        input_dataset=InputDataset.PILOT,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=disposition,
        corpus_id=CorpusId.LEARNING_EVIDENCE,
        reason_codes=reasons,
        candidate=candidate,
    )


def adapt_pilot(path: Path, workspace_root: Path) -> list[FusionOutcome]:
    outcomes: list[FusionOutcome] = []
    for record in iter_jsonl(path):
        try:
            outcome = _adapt_record(record, workspace_root)
        except (TypeError, ValueError) as exc:
            outcome = FusionOutcome(
                input_dataset=InputDataset.PILOT,
                input_line=record.line_number,
                raw_line_sha256=_raw_hash(record.raw),
                disposition=FusionDisposition.REJECTED,
                reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
                error=str(exc),
            )
        outcomes.append(outcome)
    return outcomes
```

- [ ] **Step 5: Run pilot adapter checks**

Run:

```powershell
uv run pytest tests/unit/fusion/test_pilot.py -v
uv run ruff check src/skillforge_kb/fusion tests/unit/fusion
uv run mypy src/skillforge_kb/fusion
```

Expected: all commands exit 0; pilot tests report 3 passed.

- [ ] **Step 6: Commit the pilot adapter**

```powershell
git add src/skillforge_kb/fusion/jsonl.py src/skillforge_kb/fusion/pilot.py tests/unit/fusion/test_pilot.py
git commit -m "feat: adapt provenance-rich pilot chunks"
```

---

### Task 3: Adapt and Route the Legacy Search Index Dataset

**Files:**
- Create: `src/skillforge_kb/fusion/legacy.py`
- Test: `tests/unit/fusion/test_legacy.py`

**Interfaces:**
- Consumes: `iter_jsonl(path)`, fusion models, and `sha256_text`.
- Produces: `classify_corpus(source_title)`, `detect_language(text)`, and `adapt_legacy(path) -> list[FusionOutcome]`.

- [ ] **Step 1: Write failing legacy adapter tests**

Create `tests/unit/fusion/test_legacy.py`:

```python
import json
from pathlib import Path

from skillforge_kb.domain.enums import Language
from skillforge_kb.fusion.legacy import adapt_legacy, classify_corpus
from skillforge_kb.fusion.models import CorpusId, FusionDisposition, ReasonCode


def _row(chunk_id: str, title: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": f"doc-{title}",
        "source_title": title,
        "heading_path": [title, "Section"],
        "text": text,
        "page_no": None,
        "domain_tag": "ai-knowledge",
        "difficulty": "进阶",
        "token_count": len(text),
    }


def test_legacy_adapter_routes_domains_and_marks_missing_provenance(tmp_path: Path) -> None:
    rows = [
        _row("paper-1", "RAG", "Retrieval augmented generation combines retrieval and generation."),
        _row("agent-1", "langchain部署", "LangChain deployment requires explicit runtime configuration."),
        _row("project-1", "校园项目_实训手册", "项目手册记录课程实施步骤和内部验收方法。"),
    ]
    path = tmp_path / "index_chunks.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    outcomes = adapt_legacy(path)

    assert [outcome.corpus_id for outcome in outcomes] == [
        CorpusId.LEARNING_EVIDENCE,
        CorpusId.AGENT_ENGINEERING,
        CorpusId.PROJECT_MATERIAL,
    ]
    assert all(outcome.disposition is FusionDisposition.REFERENCE_ONLY for outcome in outcomes)
    assert all(ReasonCode.MISSING_PROVENANCE in outcome.reason_codes for outcome in outcomes)
    assert outcomes[0].candidate is not None
    assert outcomes[0].candidate.language is Language.EN
    assert outcomes[0].candidate.source.source_key == "source:paper_rag_2020"


def test_legacy_adapter_rejects_short_text_and_supersedes_exact_duplicate(
    tmp_path: Path,
) -> None:
    duplicate_text = "Embedding models map related text to nearby vectors in representation space."
    rows = [
        _row("short", "faiss_intro", "title"),
        _row("first", "faiss_intro", duplicate_text),
        _row("second", "faiss_intro", duplicate_text),
    ]
    path = tmp_path / "index_chunks.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    outcomes = adapt_legacy(path)

    assert outcomes[0].disposition is FusionDisposition.REJECTED
    assert ReasonCode.TEXT_TOO_SHORT in outcomes[0].reason_codes
    assert outcomes[1].disposition is FusionDisposition.REFERENCE_ONLY
    assert outcomes[2].disposition is FusionDisposition.SUPERSEDED
    assert ReasonCode.EXACT_DUPLICATE in outcomes[2].reason_codes


def test_corpus_classifier_keeps_knowledge_manual_in_learning_domain() -> None:
    assert classify_corpus("GAN生成对抗网络_知识点手册") is CorpusId.LEARNING_EVIDENCE
```

- [ ] **Step 2: Run legacy tests and confirm missing-module failure**

Run:

```powershell
uv run pytest tests/unit/fusion/test_legacy.py -v
```

Expected: collection fails because `skillforge_kb.fusion.legacy` does not exist.

- [ ] **Step 3: Implement domain routing, language detection, and legacy adaptation**

Create `src/skillforge_kb/fusion/legacy.py`:

```python
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from skillforge_kb.domain.enums import Language
from skillforge_kb.ingestion.normalize import sha256_text

from .jsonl import JsonlRecord, iter_jsonl
from .models import (
    ChunkCandidate,
    CorpusId,
    FusionDisposition,
    FusionOutcome,
    InputDataset,
    ReasonCode,
    SourceCandidate,
)

AUTHORITATIVE_ALIASES = {
    "LoRA_2021": "paper_lora_2021",
    "RAG": "paper_rag_2020",
}
LEARNING_TITLES = {"Graphrag", "LoRA_2021", "QLora", "RAG"}
PROJECT_MARKERS = ("实训手册", "渐进式", "项目", "exploration_summary")


def _raw_hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def classify_corpus(source_title: str) -> CorpusId:
    if source_title in LEARNING_TITLES or "知识点手册" in source_title:
        return CorpusId.LEARNING_EVIDENCE
    if source_title.startswith("ch") and source_title.endswith("_summary"):
        return CorpusId.PROJECT_MATERIAL
    if any(marker in source_title for marker in PROJECT_MARKERS):
        return CorpusId.PROJECT_MATERIAL
    return CorpusId.AGENT_ENGINEERING


def detect_language(text: str) -> Language:
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    alpha_count = len(re.findall(r"[A-Za-z]", text))
    return Language.ZH if cjk_count >= alpha_count else Language.EN


def _invalid(record: JsonlRecord) -> FusionOutcome:
    return FusionOutcome(
        input_dataset=InputDataset.LEGACY_INDEX,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=FusionDisposition.REJECTED,
        reason_codes=[ReasonCode.INVALID_JSON],
        error=record.error,
    )


def _adapt_record(record: JsonlRecord, seen_hashes: set[str]) -> FusionOutcome:
    if record.value is None:
        return _invalid(record)
    row: dict[str, Any] = record.value
    required = ("chunk_id", "doc_id", "source_title", "text")
    missing = [field for field in required if not row.get(field)]
    if missing:
        return FusionOutcome(
            input_dataset=InputDataset.LEGACY_INDEX,
            input_line=record.line_number,
            raw_line_sha256=_raw_hash(record.raw),
            disposition=FusionDisposition.REJECTED,
            reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
            error=f"missing required fields: {', '.join(missing)}",
        )

    text = str(row["text"])
    title = str(row["source_title"])
    corpus_id = classify_corpus(title)
    normalized_hash = sha256_text(text)
    reasons = [ReasonCode.MISSING_PROVENANCE, ReasonCode.HUMAN_REVIEW_REQUIRED]
    disposition = FusionDisposition.REFERENCE_ONLY
    if row.get("token_count") == len(text):
        reasons.append(ReasonCode.TOKEN_COUNT_IS_CHARACTER_COUNT)
    if len(text) < 20:
        reasons.append(ReasonCode.TEXT_TOO_SHORT)
        disposition = FusionDisposition.REJECTED
    elif normalized_hash in seen_hashes:
        reasons.append(ReasonCode.EXACT_DUPLICATE)
        disposition = FusionDisposition.SUPERSEDED
    elif len(text) > 2_000:
        reasons.append(ReasonCode.TEXT_REQUIRES_RECHUNKING)
    seen_hashes.add(normalized_hash)

    source_id = AUTHORITATIVE_ALIASES.get(title, f"legacy-{row['doc_id']}")
    if title in AUTHORITATIVE_ALIASES:
        reasons.append(ReasonCode.OVERLAPS_AUTHORITATIVE_SOURCE)
    source = SourceCandidate(
        source_key=f"source:{source_id}",
        source_id=source_id,
        title=title,
        corpus_id=corpus_id,
        provenance_complete=False,
        input_dataset=InputDataset.LEGACY_INDEX,
        input_line=record.line_number,
    )
    heading_path = [str(item) for item in row.get("heading_path", [])]
    page_no = row.get("page_no")
    locator = f"page {page_no}" if page_no is not None else " > ".join(heading_path) or None
    candidate = ChunkCandidate(
        chunk_id=str(row["chunk_id"]),
        source=source,
        language=detect_language(text),
        text=text,
        locator=locator,
        difficulty=None,
        normalized_hash=normalized_hash,
        metadata={
            "legacy_difficulty": row.get("difficulty"),
            "legacy_domain_tag": row.get("domain_tag"),
            "legacy_token_count": row.get("token_count"),
        },
    )
    return FusionOutcome(
        input_dataset=InputDataset.LEGACY_INDEX,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=disposition,
        corpus_id=corpus_id,
        reason_codes=reasons,
        candidate=candidate,
    )


def adapt_legacy(path: Path) -> list[FusionOutcome]:
    seen_hashes: set[str] = set()
    outcomes: list[FusionOutcome] = []
    for record in iter_jsonl(path):
        try:
            outcome = _adapt_record(record, seen_hashes)
        except (TypeError, ValueError) as exc:
            outcome = FusionOutcome(
                input_dataset=InputDataset.LEGACY_INDEX,
                input_line=record.line_number,
                raw_line_sha256=_raw_hash(record.raw),
                disposition=FusionDisposition.REJECTED,
                reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
                error=str(exc),
            )
        outcomes.append(outcome)
    return outcomes
```

- [ ] **Step 4: Run legacy adapter checks**

Run:

```powershell
uv run pytest tests/unit/fusion/test_legacy.py -v
uv run ruff check src/skillforge_kb/fusion tests/unit/fusion
uv run mypy src/skillforge_kb/fusion
```

Expected: all commands exit 0; legacy tests report 3 passed.

- [ ] **Step 5: Commit the legacy adapter**

```powershell
git add src/skillforge_kb/fusion/legacy.py tests/unit/fusion/test_legacy.py
git commit -m "feat: classify legacy index candidates"
```

---

### Task 4: Generate Atomic Fusion Reports

**Files:**
- Create: `src/skillforge_kb/fusion/runner.py`
- Test: `tests/unit/fusion/test_runner.py`

**Interfaces:**
- Consumes: `adapt_pilot`, `adapt_legacy`, `inventory_tree`, and four paths: knowledge root, legacy root, pilot JSONL, and legacy JSONL.
- Produces: `run_dry_run(...) -> DryRunSummary` and four deterministic files: `input_inventory.jsonl`, `source_candidates.jsonl`, `fusion_outcomes.jsonl`, and `fusion_summary.json`.

- [ ] **Step 1: Write the failing orchestrator test**

Create `tests/unit/fusion/test_runner.py`:

```python
import json
from pathlib import Path

from skillforge_kb.fusion.runner import run_dry_run
from skillforge_kb.ingestion.normalize import sha256_text


def _pilot_row(source_path: str) -> dict[str, object]:
    text = "矩阵乘法把输入特征映射到新的表示空间，并保持线性结构。"
    return {
        "chunk_id": "pilot-1",
        "source_id": "source-1",
        "source_title": "Linear Algebra Notes",
        "source_path": source_path,
        "source_url": "https://example.edu/linear-algebra",
        "language": "zh",
        "text": text,
        "content_hash": sha256_text(text),
        "locator": "page 1",
        "concept_ids": ["ml.linear_algebra.matrix"],
        "content_kind": "definition",
        "difficulty": 2,
        "license": "MIT",
        "review_status": "candidate",
    }


def _legacy_row(chunk_id: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": "legacy-doc",
        "source_title": "faiss_intro",
        "heading_path": ["FAISS", "IndexFlatIP"],
        "text": text,
        "page_no": None,
        "domain_tag": "ai-knowledge",
        "difficulty": "进阶",
        "token_count": len(text),
    }


def test_dry_run_accounts_for_every_line_and_is_deterministic(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "knowledge"
    legacy_root = tmp_path / "processed"
    output_dir = tmp_path / "reports"
    knowledge_root.mkdir()
    legacy_root.mkdir()
    (knowledge_root / "source.pdf").write_bytes(b"source")
    pilot_path = knowledge_root / "pilot.jsonl"
    pilot_path.write_text(
        json.dumps(_pilot_row("knowledge/source.pdf"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    legacy_text = "IndexFlatIP performs exact inner-product retrieval over normalized vectors."
    legacy_path = legacy_root / "index_chunks.jsonl"
    legacy_path.write_text(
        json.dumps(_legacy_row("legacy-1", legacy_text), ensure_ascii=False)
        + "\n"
        + json.dumps(_legacy_row("legacy-2", legacy_text), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    first = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_path,
        legacy_jsonl=legacy_path,
        workspace_root=tmp_path,
        output_dir=output_dir,
    )
    first_bytes = {
        path.name: path.read_bytes() for path in sorted(output_dir.iterdir()) if path.is_file()
    }
    second = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_path,
        legacy_jsonl=legacy_path,
        workspace_root=tmp_path,
        output_dir=output_dir,
    )

    assert first == second
    assert first.input_rows == 3
    assert sum(first.outcome_counts.values()) == 3
    assert first.source_count == 2
    assert first_bytes == {
        path.name: path.read_bytes() for path in sorted(output_dir.iterdir()) if path.is_file()
    }
    outcomes = [
        json.loads(line)
        for line in (output_dir / "fusion_outcomes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(outcomes) == 3
    assert all(outcome["publishable"] is False for outcome in outcomes)
```

- [ ] **Step 2: Run the orchestrator test and confirm missing-module failure**

Run:

```powershell
uv run pytest tests/unit/fusion/test_runner.py -v
```

Expected: collection fails because `skillforge_kb.fusion.runner` does not exist.

- [ ] **Step 3: Implement deterministic source reconciliation and atomic writers**

Create `src/skillforge_kb/fusion/runner.py`:

```python
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .inventory import inventory_tree
from .legacy import adapt_legacy
from .models import DryRunSummary, FusionOutcome, SourceCandidate
from .pilot import adapt_pilot


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _json_line(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, values: Iterable[Any]) -> None:
    lines = [_json_line(value) for value in values]
    _atomic_write(path, "".join(f"{line}\n" for line in lines))


def _source_score(source: SourceCandidate) -> tuple[int, int, int]:
    return (
        int(source.provenance_complete),
        int(source.canonical_url is not None),
        int(source.source_path is not None),
    )


def _sources(outcomes: list[FusionOutcome]) -> list[SourceCandidate]:
    selected: dict[str, SourceCandidate] = {}
    for outcome in outcomes:
        if outcome.candidate is None:
            continue
        source = outcome.candidate.source
        current = selected.get(source.source_key)
        if current is None or _source_score(source) > _source_score(current):
            selected[source.source_key] = source
    return [selected[key] for key in sorted(selected)]


def _counter(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def run_dry_run(
    *,
    knowledge_root: Path,
    legacy_root: Path,
    pilot_jsonl: Path,
    legacy_jsonl: Path,
    workspace_root: Path,
    output_dir: Path,
) -> DryRunSummary:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = inventory_tree(knowledge_root) + inventory_tree(legacy_root)
    inventory.sort(key=lambda entry: (entry.root, entry.relative_path))
    outcomes = adapt_pilot(pilot_jsonl, workspace_root) + adapt_legacy(legacy_jsonl)
    sources = _sources(outcomes)
    summary = DryRunSummary(
        input_rows=len(outcomes),
        source_count=len(sources),
        input_file_count=len(inventory),
        outcome_counts=_counter(outcome.disposition.value for outcome in outcomes),
        reason_counts=_counter(
            reason.value for outcome in outcomes for reason in outcome.reason_codes
        ),
        corpus_counts=_counter(
            outcome.corpus_id.value for outcome in outcomes if outcome.corpus_id is not None
        ),
    )
    _write_jsonl(output_dir / "input_inventory.jsonl", inventory)
    _write_jsonl(output_dir / "source_candidates.jsonl", sources)
    _write_jsonl(output_dir / "fusion_outcomes.jsonl", outcomes)
    _atomic_write(
        output_dir / "fusion_summary.json",
        json.dumps(
            summary.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return summary
```

- [ ] **Step 4: Run report-generation checks**

Run:

```powershell
uv run pytest tests/unit/fusion/test_runner.py -v
uv run pytest tests/unit/fusion -v
uv run ruff check src/skillforge_kb/fusion tests/unit/fusion
uv run mypy src/skillforge_kb/fusion
```

Expected: all commands exit 0; the full fusion unit suite reports 9 passed.

- [ ] **Step 5: Commit the orchestrator**

```powershell
git add src/skillforge_kb/fusion/runner.py tests/unit/fusion/test_runner.py
git commit -m "feat: generate deterministic fusion reports"
```

---

### Task 5: Expose the Dry Run CLI and Verify the Real 2,133-Row Intake

**Files:**
- Create: `src/skillforge_kb/cli.py`
- Create: `tests/unit/test_cli.py`
- Generate, ignored: `reports/generated/fusion-v1/input_inventory.jsonl`
- Generate, ignored: `reports/generated/fusion-v1/source_candidates.jsonl`
- Generate, ignored: `reports/generated/fusion-v1/fusion_outcomes.jsonl`
- Generate, ignored: `reports/generated/fusion-v1/fusion_summary.json`

**Interfaces:**
- Consumes: `run_dry_run(...)` and filesystem paths supplied as Typer options.
- Produces: `skillforge-kb fusion-dry-run` and a verified real-data dry-run report.

- [ ] **Step 1: Write the failing CLI test**

Create `tests/unit/test_cli.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb.cli import app
from skillforge_kb.ingestion.normalize import sha256_text

runner = CliRunner()


def test_fusion_dry_run_cli_writes_summary(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    processed = tmp_path / "processed"
    output = tmp_path / "output"
    knowledge.mkdir()
    processed.mkdir()
    source = knowledge / "source.pdf"
    source.write_bytes(b"source")
    text = "梯度下降沿损失函数下降方向更新模型参数。"
    pilot_row = {
        "chunk_id": "pilot-1",
        "source_id": "source-1",
        "source_title": "Optimization Notes",
        "source_path": "knowledge/source.pdf",
        "source_url": "https://example.edu/optimization",
        "language": "zh",
        "text": text,
        "content_hash": sha256_text(text),
        "locator": "page 1",
        "concept_ids": ["ml.optimization.gradient_descent"],
        "content_kind": "definition",
        "difficulty": 2,
        "license": "MIT",
        "review_status": "candidate",
    }
    pilot = knowledge / "pilot.jsonl"
    pilot.write_text(json.dumps(pilot_row, ensure_ascii=False) + "\n", encoding="utf-8")
    legacy = processed / "index_chunks.jsonl"
    legacy.write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "fusion-dry-run",
            "--knowledge-root",
            str(knowledge),
            "--legacy-root",
            str(processed),
            "--pilot-jsonl",
            str(pilot),
            "--legacy-jsonl",
            str(legacy),
            "--workspace-root",
            str(tmp_path),
            "--output-dir",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "Processed 1 rows" in result.stdout
    summary = json.loads((output / "fusion_summary.json").read_text(encoding="utf-8"))
    assert summary["input_rows"] == 1
```

- [ ] **Step 2: Run the CLI test and confirm missing-module failure**

Run:

```powershell
uv run pytest tests/unit/test_cli.py -v
```

Expected: collection fails because `skillforge_kb.cli` does not exist.

- [ ] **Step 3: Implement the Typer command**

Create `src/skillforge_kb/cli.py`:

```python
from pathlib import Path
from typing import Annotated

import typer

from skillforge_kb.fusion.runner import run_dry_run

app = typer.Typer(no_args_is_help=True)


@app.command("fusion-dry-run")
def fusion_dry_run(
    knowledge_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    legacy_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    pilot_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    legacy_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    workspace_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    summary = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_jsonl,
        legacy_jsonl=legacy_jsonl,
        workspace_root=workspace_root,
        output_dir=output_dir,
    )
    typer.echo(f"Processed {summary.input_rows} rows into {output_dir.resolve()}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run focused and full static checks**

Run:

```powershell
uv run pytest tests/unit/test_cli.py tests/unit/fusion -v
uv run pytest tests/unit -v
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
```

Expected: all commands exit 0. The focused suite reports 10 passed; the complete unit suite has no failures.

- [ ] **Step 5: Commit the CLI**

```powershell
git add src/skillforge_kb/cli.py tests/unit/test_cli.py
git commit -m "feat: expose knowledge fusion dry run"
```

- [ ] **Step 6: Execute the real read-only fusion intake**

Run from `D:\张维揭榜挂帅\.worktrees\kb-v1`:

```powershell
uv run skillforge-kb fusion-dry-run `
  --knowledge-root 'D:\张维揭榜挂帅\知识库' `
  --legacy-root 'D:\张维揭榜挂帅\processed' `
  --pilot-jsonl 'D:\张维揭榜挂帅\知识库\processed\chunks\ai_learning_pilot_chunks.jsonl' `
  --legacy-jsonl 'D:\张维揭榜挂帅\processed\index_chunks.jsonl' `
  --workspace-root 'D:\张维揭榜挂帅' `
  --output-dir 'reports/generated/fusion-v1'
```

Expected: exit 0 and stdout contains `Processed 2133 rows`.

- [ ] **Step 7: Verify report completeness and source immutability**

Run:

```powershell
$summary = Get-Content -Raw 'reports/generated/fusion-v1/fusion_summary.json' | ConvertFrom-Json
if ($summary.input_rows -ne 2133) { throw "Expected 2133 outcomes" }
$outcomeLines = (Get-Content 'reports/generated/fusion-v1/fusion_outcomes.jsonl').Count
if ($outcomeLines -ne 2133) { throw "Expected 2133 JSONL outcome lines" }
if (($summary.outcome_counts.PSObject.Properties.Value | Measure-Object -Sum).Sum -ne 2133) {
  throw "Outcome counts do not sum to 2133"
}
Get-FileHash -Algorithm SHA256 `
  'D:\张维揭榜挂帅\知识库\processed\chunks\ai_learning_pilot_chunks.jsonl', `
  'D:\张维揭榜挂帅\processed\index_chunks.jsonl'
git status --short
```

Expected: all assertions pass. Git status lists only the three pre-existing PostgreSQL-related modifications; generated reports remain ignored. Record the two input hashes in the completion report so later runs can prove that the audited inputs are unchanged.

- [ ] **Step 8: Run final regression checks**

Run:

```powershell
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
git diff --check
```

Expected: all commands exit 0 with no unit-test failures, lint errors, type errors, or whitespace errors.
