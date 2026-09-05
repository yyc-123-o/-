# External Knowledge Base Cross-Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `data/external/index_chunks(1).jsonl` into a read-only external verification source that can be compared against the primary corpus to detect agreement, conflicts, and coverage gaps without changing formal evidence publication.

**Architecture:** Reuse the existing `KnowledgeCorpus`, concept-binding, and evidence-governance code paths. The external JSONL is loaded as a second read-only corpus, normalized only enough to support concept binding and content-kind inference, then compared against the primary corpus to produce a deterministic JSON audit report. No external row is promoted to formal evidence, and no vector index is required for this phase.

**Tech Stack:** Python, Pydantic, existing `KnowledgeCorpus`, `OntologyCatalog`, `build_candidate_bindings`, `build_review_queue`, pytest, Typer/argparse for CLI.

## Global Constraints

- `data/external/index_chunks(1).jsonl` is read-only input and must never be mutated in place.
- The external corpus remains candidate-only; it must not generate `EvidenceRecord` or publishable manifest rows.
- Do not add a dense/vector indexing requirement for the external corpus.
- Keep existing primary-corpus retrieval, evidence manifest, and publication gates unchanged.
- Every report must be deterministic, JSON serializable, and safe to regenerate from the same inputs.
- Any content-kind inference for missing rows must be explicitly marked as inferred, never silently treated as authoritative.

---

### Task 1: Add an external-corpus adapter and summary model

**Files:**
- Create: `src/skillforge_kb/evidence/external_corpus.py`
- Modify: `src/skillforge_kb/evidence/__init__.py`
- Test: `tests/unit/evidence/test_external_corpus.py`

**Interfaces:**
- `load_external_corpus(path: Path) -> ExternalCorpus`
- `ExternalCorpus.records`
- `ExternalCorpus.missing_content_kind_count`
- `ExternalCorpus.record_count`
- `ExternalCorpus.to_knowledge_corpus() -> KnowledgeCorpus`
- `infer_external_content_kind(text: str, heading_path: tuple[str, ...], declared_kind: str | None) -> tuple[str, str]`

- [ ] **Step 1: Write the failing test**

```python
def test_load_external_corpus_marks_missing_content_kind_and_keeps_counts(tmp_path: Path) -> None:
    sample = tmp_path / "external.jsonl"
    sample.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "chunk_id": "ext-1",
                        "doc_id": "doc-1",
                        "source_title": "CNN Intro",
                        "heading_path": ["CNN", "卷积"],
                        "text": "卷积核在输入上滑动并生成输出特征图。",
                        "page_no": 1,
                        "domain_tag": "ai-knowledge",
                        "difficulty": "进阶",
                        "token_count": 12,
                        "content_kind": "definition",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "chunk_id": "ext-2",
                        "doc_id": "doc-2",
                        "source_title": "CNN Code",
                        "heading_path": ["CNN", "Conv2d"],
                        "text": "torch.nn.Conv2d(3, 8, kernel_size=3, stride=1, padding=1)",
                        "page_no": 2,
                        "domain_tag": "ai-knowledge",
                        "difficulty": "进阶",
                        "token_count": 10
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    corpus = load_external_corpus(sample)

    assert corpus.record_count == 2
    assert corpus.missing_content_kind_count == 1
    assert corpus.records[0].content_kind_source == "declared"
    assert corpus.records[1].content_kind_source == "inferred"
    assert corpus.to_knowledge_corpus().digest
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `pytest tests/unit/evidence/test_external_corpus.py -v`

Expected: fail because `external_corpus.py` does not exist yet.

- [ ] **Step 3: Implement the minimal adapter**

Implement a thin loader that:

```python
class ExternalCorpus(BaseModel):
    records: tuple[ExternalCorpusRecord, ...]
    digest: str
```

Each record should preserve raw provenance and normalize:

- `source_id` from `doc_id`
- `difficulty` to `intro` / `intermediate` / `advanced`
- `license_status` to `metadata_only`
- `review_status` to `candidate`
- `evidence_status` to `external_candidate`
- `content_kind` to declared value when present; otherwise infer conservatively and mark `content_kind_source="inferred"`

- [ ] **Step 4: Run the test and confirm it passes**

Run: `pytest tests/unit/evidence/test_external_corpus.py -v`

Expected: pass.


### Task 2: Build the cross-check report engine

**Files:**
- Create: `src/skillforge_kb/evidence/cross_check.py`
- Modify: `src/skillforge_kb/evidence/__init__.py`
- Test: `tests/unit/evidence/test_cross_check.py`

**Interfaces:**
- `build_cross_check_report(primary: KnowledgeCorpus, external: KnowledgeCorpus, catalog: OntologyCatalog, *, core_concept_ids: Sequence[str] | None = None) -> dict[str, object]`
- `CrossCheckRow`
- `CrossCheckSummary`
- `write_cross_check_report(report: Mapping[str, object], output_path: Path) -> None`

- [ ] **Step 1: Write the failing test**

```python
def test_cross_check_report_separates_agreement_conflict_and_gaps(catalog, tmp_path: Path) -> None:
    primary = KnowledgeCorpus.load(tmp_path / "primary.jsonl")
    external = KnowledgeCorpus.load(tmp_path / "external.jsonl")

    report = build_cross_check_report(primary, external, catalog, core_concept_ids=["dl.cnn.convolution"])

    assert report["summary"]["agreement_count"] == 1
    assert report["summary"]["conflict_count"] == 1
    assert report["summary"]["external_only_count"] == 1
    assert report["summary"]["primary_only_count"] == 0
    assert report["summary"]["duplicate_overlap_count"] == 1
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `pytest tests/unit/evidence/test_cross_check.py -v`

Expected: fail because the cross-check engine does not exist yet.

- [ ] **Step 3: Implement the cross-check logic**

Use the existing `build_candidate_bindings(catalog, corpus)` helper on both corpora, then compare:

- identical normalized text → `duplicate_overlap`
- same concept binding and same inferred kind → `agreement`
- same concept binding but different kind → `conflict`
- only primary bindings → `primary_only`
- only external bindings → `external_only`
- ambiguous or weak bindings → `needs_review`

The report must include:

- request metadata
- per-concept evidence counts
- content-kind coverage
- conflict rows with both chunk IDs
- duplicate overlap rows
- deterministic ordering by concept ID and chunk ID

- [ ] **Step 4: Run the test and confirm it passes**

Run: `pytest tests/unit/evidence/test_cross_check.py -v`

Expected: pass.


### Task 3: Expose a CLI and a documented output contract

**Files:**
- Create: `scripts/build_external_cross_check_report.py`
- Modify: `docs/data/external-corpus-usage.md` or create `docs/data/external-corpus-cross-check.md`
- Test: `tests/acceptance/test_external_cross_check_report.py`

**Interfaces:**
- CLI arguments: `--primary-file`, `--external-file`, `--course-file`, `--relations-file`, `--output-file`, `--core-concept-id`
- The CLI writes a single JSON report and prints a compact summary to stdout.

- [ ] **Step 1: Write the failing test**

```python
def test_external_cross_check_cli_writes_json_report(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_external_cross_check_report.py",
            "--primary-file",
            "data/index_chunks.jsonl",
            "--external-file",
            "data/external/index_chunks(1).jsonl",
            "--output-file",
            str(tmp_path / "cross_check_report.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads((tmp_path / "cross_check_report.json").read_text(encoding="utf-8"))
    assert payload["summary"]["agreement_count"] >= 0
    assert payload["gate_decision"]["allowed_for_published_resource"] is False
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `pytest tests/acceptance/test_external_cross_check_report.py -v`

Expected: fail because the CLI does not exist yet.

- [ ] **Step 3: Implement the CLI and documentation**

The script should:

- load both corpora
- build the cross-check report
- write JSON with stable formatting
- keep the gate decision explicit: draft-use may be allowed, published-use remains false until human review

Update the short docs note to explain:

- the external corpus is a verification source only
- it is not a replacement for the primary corpus
- it is not vectorized in this phase
- it can be used to explain agreement, conflict, and missing coverage

- [ ] **Step 4: Run the test and confirm it passes**

Run: `pytest tests/acceptance/test_external_cross_check_report.py -v`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/evidence/external_corpus.py \
        src/skillforge_kb/evidence/cross_check.py \
        src/skillforge_kb/evidence/__init__.py \
        scripts/build_external_cross_check_report.py \
        tests/unit/evidence/test_external_corpus.py \
        tests/unit/evidence/test_cross_check.py \
        tests/acceptance/test_external_cross_check_report.py \
        docs/data/external-corpus-usage.md
git commit -m "feat: add external corpus cross-check report"
```

## Self-Review Checklist

- The plan covers loading, normalization, comparison, CLI exposure, and docs.
- No task promotes the external corpus into formal evidence.
- No task introduces a vector index requirement.
- Test files are paired with each code path.
- Every output is deterministic and JSON serializable.
