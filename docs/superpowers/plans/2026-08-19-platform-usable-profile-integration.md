# Platform Usable Profile Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely consume the imported Learner Profile Agent and enforce true candidate evidence types in the local platform.

**Architecture:** A versioned profile adapter converts only explicit atomic knowledge-point mappings into `LearnerProfileSnapshot`; an API endpoint exposes that conversion separately from run execution. Retrieval candidates use declared or conservative inferred content kinds and never infer type from the query label alone.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest, existing LangGraph platform.

## Global Constraints

- Strict generation requires reviewed, licensed, published evidence.
- Candidate evidence never becomes formal evidence.
- Planner identity, path order, graph version, and depth remain authoritative.
- Unmapped or composite profile IDs are reported and omitted, not guessed.
- Existing deterministic baseline remains the fallback.

### Task 1: Profile Agent Adapter Contract

**Files:**
- Create: `src/skillforge_kb/ontology/profile_agent_adapter.py`
- Create: `resources/ontology/profile_agent_kp_map_v1.yaml`
- Test: `tests/unit/ontology/test_profile_agent_adapter.py`

**Interfaces:**
- `LearnerProfileAgentAdapter(catalog, mappings).adapt(raw: Mapping[str, object]) -> AdaptedLearnerProfile`
- `AdaptedLearnerProfile.snapshot: LearnerProfileSnapshot`
- `AdaptedLearnerProfile.warnings: tuple[ProfileAdaptationWarning, ...]`

- [ ] **Step 1: Write failing tests** for CNN mapping, warning on unmapped IDs, graph mismatch, malformed v2.1 input, and exclusion of downstream resource hints.
- [ ] **Step 2: Run** `uv run pytest tests/unit/ontology/test_profile_agent_adapter.py -q`; expect collection/import failure because the adapter does not exist.
- [ ] **Step 3: Implement** strict Pydantic validation, explicit mapping loading, canonical field conversion, and warning collection.
- [ ] **Step 4: Run** the focused test and expect all adapter tests to pass.
- [ ] **Step 5: Commit** `feat: adapt learner profile agent output`.

### Task 2: Candidate Content-Type Enforcement

**Files:**
- Modify: `src/skillforge_kb/retrieval/models.py`
- Modify: `src/skillforge_kb/agents/retrieval_agent.py`
- Test: `tests/unit/agents/test_retrieval_agent.py`
- Test: `tests/unit/retrieval/test_corpus.py`

**Interfaces:**
- `KnowledgeChunk.content_kind: ContentKind | None`
- `_infer_content_kind(chunk: KnowledgeChunk) -> ContentKind`

- [ ] **Step 1: Write failing regression tests** proving one code chunk is not emitted as exercise or definition and ambiguous chunks do not satisfy exercise.
- [ ] **Step 2: Run** the focused tests; expect the current query-label behavior to fail the assertions.
- [ ] **Step 3: Implement** declared-kind precedence and conservative text/heading inference.
- [ ] **Step 4: Run** retrieval and platform integration tests; update candidate-preview assertions to require typed candidates.
- [ ] **Step 5: Commit** `fix: enforce candidate evidence content kinds`.

### Task 3: FastAPI Adaptation Endpoint

**Files:**
- Modify: `src/skillforge_kb/api/app.py`
- Modify: `src/skillforge_kb/api/static/app.js`
- Test: `tests/unit/api/test_app.py`
- Test: `tests/acceptance/test_profile_agent_api.py`

**Interfaces:**
- `ProfileAdaptationService` protocol with `adapt(raw) -> AdaptedLearnerProfile`.
- `POST /api/v1/profiles/adapt` returns snapshot, warnings, adapter version, and source version.

- [ ] **Step 1: Write failing API tests** for successful CNN conversion, 422 malformed profile, and 422 graph mismatch.
- [ ] **Step 2: Run** focused API tests and confirm the route is missing.
- [ ] **Step 3: Implement** dependency injection in `create_app` without changing `/api/v1/runs`.
- [ ] **Step 4: Run** API and acceptance tests.
- [ ] **Step 5: Commit** `feat: expose learner profile adaptation endpoint`.

### Task 4: Runtime Wiring and Documentation

**Files:**
- Modify: `src/skillforge_kb/platform/runtime.py`
- Modify: `README.md`
- Modify: `docs/integrations/learner-profile-agent-import.md`
- Test: `tests/acceptance/test_profile_agent_api.py`

- [ ] **Step 1: Write a failing acceptance test** that builds the default app with the imported profile adapter and reaches the CNN planner node after adaptation.
- [ ] **Step 2: Run** the acceptance test and confirm the default service has no profile-adaptation dependency.
- [ ] **Step 3: Wire** the versioned map and adapter into the default API factory, documenting the two-step adapt-then-run flow.
- [ ] **Step 4: Run** unit, acceptance, Ruff, mypy, and `git diff --check`.
- [ ] **Step 5: Commit** `feat: wire profile adapter into platform runtime`.
