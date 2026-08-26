# Concept Resource Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate auditable candidate bindings from teammate knowledge chunks to existing course concepts without changing the course ontology or publishing evidence.

**Architecture:** Add a focused binding module under `skillforge_kb.binding` with immutable Pydantic models and deterministic name/alias matching. Add a script that loads the existing ontology and candidate corpus, writes JSONL candidate edges and a coverage report, and add unit/integration tests.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, pytest, existing `OntologyCatalog` and `KnowledgeCorpus`.

## Global Constraints

- Core chapter, section, concept, and prerequisite files remain unchanged.
- Every generated edge is `review_status=candidate` and `evidence_state=candidate`.
- Candidate edges never become `EvidenceRecord`, `EvidenceBundle`, or published graph relations.
- Inputs are read-only; outputs must be outside the input files.
- Output ordering and IDs must be deterministic.

### Task 1: Binding Models and Matcher

**Files:**
- Create: `src/skillforge_kb/binding/__init__.py`
- Create: `src/skillforge_kb/binding/models.py`
- Create: `src/skillforge_kb/binding/matcher.py`
- Test: `tests/unit/binding/test_matcher.py`

**Interfaces:**
- `build_candidate_bindings(catalog: OntologyCatalog, corpus: KnowledgeCorpus) -> tuple[ConceptResourceBinding, ...]`
- `ConceptResourceBinding` exposes `binding_id`, `chunk_id`, `concept_id`, `chapter_id`, `section_id`, `match_type`, `matched_term`, `score`, `review_status`, and `evidence_state`.

- [ ] Write tests for exact Chinese/English names, aliases, heading matches, no matches, stable order, and duplicate suppression.
- [ ] Implement immutable models and deterministic matching with title/heading matches ranked above body matches.
- [ ] Run `uv run pytest tests/unit/binding/test_matcher.py -q`.

### Task 2: Binding Report Script

**Files:**
- Create: `scripts/build_concept_resource_bindings.py`
- Modify: `src/skillforge_kb/binding/__init__.py`
- Test: `tests/acceptance/test_concept_resource_binding.py`

**Interfaces:**
- CLI arguments: `--course-file`, `--relations-file`, `--knowledge-file`, `--output-dir`.
- Outputs: `concept_resource_candidates.jsonl` and `concept_resource_binding_report.json`.

- [ ] Write an acceptance test against the real repository assets.
- [ ] Implement argument parsing, atomic writes, input digests, per-concept coverage, and candidate-only status fields.
- [ ] Run the acceptance test and the script to generate `reports/generated/concept-resource-bindings/`.

### Task 3: Documentation and Verification

**Files:**
- Create: `docs/runbooks/concept-resource-binding.md`
- Modify: `README.md`

- [ ] Document the candidate-only governance boundary and manual review promotion requirements.
- [ ] Run focused tests, full unit tests, and `ruff check` on changed Python files.
- [ ] Inspect generated report and confirm no ontology or evidence manifest changes.
