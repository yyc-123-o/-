# Evidence Governance Implementation Plan

> **For agentic workers:** Execute this plan inline with test-first checkpoints. Do not publish candidate records as formal evidence without explicit human review.

**Goal:** Build a generic, candidate-only evidence governance queue and coverage report for the AI course graph.

**Architecture:** Normalize rich teammate JSONL records against `OntologyCatalog`, reject unsafe records with deterministic reasons, and emit a review queue. The queue remains separate from `EvidenceIndex`; only a later explicit publication step may create `EvidenceRecord` entries.

**Tech Stack:** Python 3.12, Pydantic domain enums, existing `OntologyCatalog`, pytest, argparse.

## Global Constraints

- Candidate records must remain `review_status=candidate` and `publishable=false`.
- Unknown concept IDs and missing provenance are excluded, never guessed.
- The existing CNN-specific API remains backward compatible.
- No input JSONL is overwritten.

---

### Task 1: Add Generic Governance Queue

**Files:**
- Create: `src/skillforge_kb/evidence/governance.py`
- Modify: `src/skillforge_kb/evidence/__init__.py`
- Test: `tests/unit/evidence/test_governance.py`

**Interfaces:**
- `build_review_queue(rows, catalog, core_concept_ids=None) -> dict[str, object]`
- `build_cnn_review_queue(rows) -> dict[str, object]` delegates to the generic function with the CNN concept.

- [ ] Write tests for valid candidates, unknown concepts, missing metadata, duplicate chunks, and coverage gaps.
- [ ] Run `pytest tests/unit/evidence/test_governance.py -q` and observe failures before implementation.
- [ ] Implement deterministic normalization, exclusion reasons, proposed depth mapping, and per-concept coverage summaries.
- [ ] Export the generic builder from `evidence.__init__`.
- [ ] Run the focused tests and then `pytest tests/unit/evidence -q`.

### Task 2: Add CLI for Candidate Queue Generation

**Files:**
- Create: `scripts/build_evidence_review_queue.py`
- Test: `tests/unit/evidence/test_governance_cli.py`

**Interfaces:**
- CLI options: `--input-file`, `--output-file`, `--course-file`, `--relations-file`, `--core-concept-id` repeatable.
- The command writes JSON only to the output path and rejects equal input/output paths.

- [ ] Write CLI tests using a temporary JSONL and ontology fixture.
- [ ] Run focused CLI tests and observe failure.
- [ ] Implement argument parsing, JSONL validation, catalog loading, and atomic output writing.
- [ ] Run CLI tests and a read-only Pilot against `知识库/processed/chunks/ai_learning_pilot_review_300.jsonl`.

### Task 3: Preserve CNN Compatibility and Document Review Boundary

**Files:**
- Modify: `src/skillforge_kb/evidence/review_queue.py`
- Modify: `tests/unit/evidence/test_review_queue.py`
- Modify: `docs/runbooks/concept-resource-binding.md`

- [ ] Add a regression test proving the CNN wrapper output remains unchanged for valid rows and exclusions.
- [ ] Replace duplicated CNN validation logic with the generic governance rule while retaining CNN-specific distractor filtering.
- [ ] Document that queue output is not formal evidence and list the manual publication prerequisites.
- [ ] Run all evidence tests and `git diff --check`.

### Task 4: Verification and Handoff

**Files:**
- Modify: `docs/data/evidence-governance-pilot.md` (create if absent)

- [ ] Record the Pilot command, candidate/excluded counts, concept coverage, and missing content kinds.
- [ ] Run `pytest tests/unit -q` and `ruff check src tests/unit`.
- [ ] Confirm `resources/evidence/evidence_manifest_v1.yaml` remains unchanged until human review.
