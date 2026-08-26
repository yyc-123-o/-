# CNN Evidence Review Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, candidate-only review queue for `dl.cnn.convolution / intro` without promoting unreviewed material into the formal evidence manifest.

**Architecture:** Read the teammate review JSONL as an external candidate source, select only rows explicitly tagged for `dl.cnn.convolution`, reject disallowed source families, and emit a compact JSON review queue with provenance and content gaps. The existing runtime and `evidence_manifest_v1.yaml` remain unchanged until a human reviewer supplies publication decisions.

**Tech Stack:** Python 3.12, standard library `argparse`/`json`/`hashlib`, pytest, Ruff, mypy.

## Global Constraints

- The queue is candidate-only; it must never emit `review_status=published`.
- GAN, DCGAN, TextCNN, diffusion, and transposed-convolution material is excluded from standard-convolution evidence.
- A complete queue requires definition, code, and exercise; missing kinds are explicit.
- The source file is external and the output path must be outside the source file.
- No changes are made to `resources/evidence/evidence_manifest_v1.yaml`.

---

### Task 1: Add Queue Builder Contracts

**Files:**
- Create: `src/skillforge_kb/evidence/review_queue.py`
- Test: `tests/unit/evidence/test_review_queue.py`

**Interfaces:**
- Consumes: JSONL rows containing `chunk_id`, `source_id`, `source_title`, `source_url`, `license_status`, `license`, `language`, `content_kind`, `concept_ids`, `locator`, `text`, and optional `page`.
- Produces: `build_cnn_review_queue(rows) -> dict[str, object]` and `write_review_queue(path, payload) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_queue_keeps_valid_definition_and_code_and_reports_exercise_gap() -> None:
    payload = build_cnn_review_queue([
        valid_definition_row(),
        valid_code_row(),
        excluded_gan_row(),
    ])

    assert payload["concept_id"] == "dl.cnn.convolution"
    assert payload["review_status"] == "candidate"
    assert [item["content_kind"] for item in payload["candidates"]] == [
        "code",
        "definition",
    ]
    assert payload["missing_content_kinds"] == ["exercise"]
    assert payload["excluded_candidates"][0]["reason"] == "disallowed_source_family"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/evidence/test_review_queue.py::test_queue_keeps_valid_definition_and_code_and_reports_exercise_gap -q`

Expected: FAIL because `skillforge_kb.evidence.review_queue` does not exist.

- [ ] **Step 3: Implement the minimal queue builder**

Implement `build_cnn_review_queue(rows)` with frozen, deterministic output. It filters the exact concept anchor, allowed license metadata, required content kinds, and CNN/convolution source anchors; it rejects disallowed source families and weak concept bindings. Accepted rows are sorted by content kind, source ID, locator, and chunk ID. The result contains `schema_version`, `concept_id`, `depth`, `review_status`, `publishable`, `candidates`, `excluded_candidates`, `available_content_kinds`, `missing_content_kinds`, and `missing_requirements`.

The output must include `schema_version`, `concept_id`, `depth`, `review_status`, `candidates`, `excluded_candidates`, and `missing_content_kinds`. Candidate rows retain source URL, license metadata, locator, hash, and a text excerpt for human review.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `uv run pytest tests/unit/evidence/test_review_queue.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the queue contract**

```powershell
git add src/skillforge_kb/evidence/review_queue.py tests/unit/evidence/test_review_queue.py
git commit -m "feat: add CNN evidence review queue"
```

### Task 2: Add the External-Input CLI

**Files:**
- Create: `scripts/build_cnn_evidence_review_queue.py`
- Create: `tests/acceptance/test_cnn_evidence_review_queue.py`

**Interfaces:**
- Consumes: `--input-file PATH` and `--output-file PATH`.
- Produces: a JSON queue report; never mutates the input or formal manifest.

- [ ] **Step 1: Write the failing CLI test**

```python
def test_review_queue_cli_writes_candidate_only_report(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_cnn_evidence_review_queue.py"),
            "--input-file", str(input_path),
            "--output-file", str(output_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["review_status"] == "candidate"
    assert report["publishable"] is False
    assert "exercise" in report["missing_content_kinds"]
```

- [ ] **Step 2: Run the CLI test to verify it fails**

Run: `uv run pytest tests/acceptance/test_domain_retrieval_agent_output.py -q`

Expected: FAIL because the queue CLI does not exist.

- [ ] **Step 3: Implement the CLI**

Use `argparse`, reject an output path equal to the input path, parse each JSONL row, call `build_cnn_review_queue`, write UTF-8 JSON atomically enough for a local report, and print the summary as JSON. Do not import or modify the runtime manifest.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/unit/evidence/test_review_queue.py tests/acceptance/test_domain_retrieval_agent_output.py -q`

Expected: PASS; the existing acceptance assertion that formal evidence count is zero remains true.

- [ ] **Step 5: Commit the CLI**

```powershell
git add scripts/build_cnn_evidence_review_queue.py tests/acceptance/test_domain_retrieval_agent_output.py
git commit -m "feat: expose CNN evidence review queue CLI"
```

### Task 3: Generate and Document the Real Queue

**Files:**
- Create: `docs/evidence/cnn-convolution-review-queue.md`
- Generate: `reports/generated/cnn-evidence-review/cnn_evidence_review_queue.json`

- [ ] **Step 1: Run the CLI against the teammate snapshot**

```powershell
uv run python scripts/build_cnn_evidence_review_queue.py `
  --input-file 'D:\张维揭榜挂帅\知识库\processed\chunks\ai_learning_pilot_review_300.jsonl' `
  --output-file reports/generated/cnn-evidence-review/cnn_evidence_review_queue.json
```

Expected: accepted definition/code candidates from `dl_ch09_cnn`, excluded disallowed candidates, and an explicit `exercise` gap.

- [ ] **Step 2: Write the human review handoff**

Document the selected chunk IDs, source/license metadata, excluded families, missing exercise requirement, and the exact fields a reviewer must provide before adding records to `evidence_manifest_v1.yaml`.

- [ ] **Step 3: Run the full verification gate**

Run: `uv run pytest tests/unit -q`, `uv run ruff check src tests/unit scripts`, `uv run mypy src/skillforge_kb`, and `git diff --check`.

- [ ] **Step 4: Commit the review artifact**

```powershell
git add src/skillforge_kb/evidence/review_queue.py scripts/build_cnn_evidence_review_queue.py tests docs/evidence
git commit -m "docs: prepare CNN evidence review handoff"
```
