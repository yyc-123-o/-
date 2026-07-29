# Personalized Planning Resource Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Connect canonical learner profiles and approved evidence to deterministic node adaptation and validated resource-generation briefs without changing the stable course path.

**Architecture:** Extend the existing ontology/profile boundary first, add a governed evidence manifest and resource blueprint layer, then implement a deterministic `NodeWeightEngine` and `ResourceBriefBuilder`. Keep the planner pure and framework-free; LangChain/LangGraph wrappers consume only `ResourceBrief` and `EvidenceBundle` after the core contracts are tested.

**Tech Stack:** Python 3.12, Pydantic 2, YAML/JSON manifests, hashlib/json canonical serialization, pytest, Ruff, mypy, existing `OntologyCatalog` and `CoursePlanner`.

## Global Constraints

- Preserve all required concept IDs, stable ordering, chapter/section positions, and existing `path_id` semantics.
- Do not write learner-derived scores, resource hints, generated text, or model output into static ontology YAML.
- Candidate evidence cannot enter `EvidenceBundle`, Neo4j, Qdrant, or resource prompts until license, locator, hash, and human review checks pass.
- Missing or low-confidence profile evidence is conservative and cannot upgrade depth or bypass hard prerequisites.
- Preferences affect format and pacing only; they never change path order, skip rules, depth thresholds, or blockers.
- Unit tests must not require Docker, Neo4j, network access, vector models, or an LLM.
- Preserve `.claude/`, `SkillForge-MA-最终方案.md`, and `学情画像输出-示例.json` as user-owned untracked files.

---

### Task 1: Complete Canonical Profile Adaptation

**Owner:** 学情画像同学 + 知识库同学 B

**Files:**
- Modify: `resources/ontology/legacy_profile_ids_v1.yaml`
- Modify: `src/skillforge_kb/ontology/profile.py`
- Modify: `src/skillforge_kb/ontology/models.py` only if a missing canonical field is proven necessary
- Test: `tests/unit/ontology/test_profile.py`
- Test: `tests/unit/ontology/test_models.py`

**Interfaces:**
- Consumes: raw team profile export, `OntologyCatalog`, `ProfileIdMapping`.
- Produces: `ProfileAdapter.adapt(raw) -> LearnerProfileSnapshot` with mastery, four abilities, error patterns, preferences, assessment runs, and evidence refs.

- [ ] Step 1: Add a failing fixture asserting the sample profile preserves abilities, error patterns, preferences, and assessment provenance.
- [ ] Step 2: Run `uv run pytest tests/unit/ontology/test_profile.py -q`; verify failure shows dropped fields or unmapped legacy IDs.
- [ ] Step 3: Add reviewed one-to-one mappings; reject composite IDs instead of duplicating scores.
- [ ] Step 4: Implement deterministic parsing for `dimension_2_ability_level`, `dimension_3_error_patterns`, `dimension_4_learning_preferences`, `assessment_runs`, and evidence refs.
- [ ] Step 5: Add regression tests for unknown IDs, composite IDs, duplicate mappings, missing confidence, and forbidden downstream fields.
- [ ] Step 6: Run `uv run pytest tests/unit/ontology -q && uv run ruff check src/skillforge_kb/ontology tests/unit/ontology && uv run mypy src/skillforge_kb/ontology`.
- [ ] Step 7: Commit `feat: complete canonical learner profile adaptation`.

### Task 2: Governed Evidence Manifest and Coverage Matrix

**Owner:** 知识库/图谱同学 A

**Files:**
- Create: `src/skillforge_kb/evidence/models.py`
- Create: `src/skillforge_kb/evidence/manifest.py`
- Create: `src/skillforge_kb/evidence/coverage.py`
- Create: `resources/evidence/evidence_manifest_v1.yaml`
- Modify: `src/skillforge_kb/domain/models.py` only for explicit shared provenance reuse
- Test: `tests/unit/evidence/test_models.py`
- Test: `tests/unit/evidence/test_manifest.py`
- Test: `tests/unit/evidence/test_coverage.py`

**Interfaces:**
- Consumes: governed `SourceRecord`, `EvidenceChunk`, candidate JSONL and current graph version.
- Produces: `EvidenceRecord`, `EvidenceIndex`, `EvidenceCoverageReport`, `EvidenceIndex.query(concept_id, depth, language, content_kind)`.

- [ ] Step 1: Write failing tests that reject missing source, locator, license, normalized hash, unknown concept/depth, and unpublished evidence queries.
- [ ] Step 2: Run `uv run pytest tests/unit/evidence -q`; verify collection or validation failures before production code.
- [ ] Step 3: Implement immutable evidence records with states `candidate`, `reviewed`, `published`, `rejected`, `revoked` and canonical `evidence_id`.
- [ ] Step 4: Implement manifest loading, graph-version validation, candidate-to-published gating, and deterministic query ordering.
- [ ] Step 5: Extend coverage reporting to concept x depth x language x content_kind with explicit gaps and unknown IDs, without modifying input JSONL.
- [ ] Step 6: Add fixtures for candidate, reviewed, published, revoked, duplicate, and cross-version records.
- [ ] Step 7: Run `uv run pytest tests/unit/evidence -q && uv run ruff check src/skillforge_kb/evidence tests/unit/evidence && uv run mypy src/skillforge_kb/evidence`.
- [ ] Step 8: Commit `feat: add governed evidence manifest`.

### Task 3: Concept Ability Attributes and Resource Blueprints

**Owner:** 知识库/图谱同学 B + 课程规划 Agent

**Files:**
- Create: `resources/ontology/concept_attributes_v1.yaml`
- Create: `resources/ontology/resource_blueprints_v1.yaml`
- Create: `src/skillforge_kb/ontology/resource_blueprints.py`
- Modify: `src/skillforge_kb/ontology/models.py` to add the frozen attribute/blueprint contracts when the manifest fields are not representable by existing models
- Modify: `src/skillforge_kb/ontology/validation.py`
- Test: `tests/unit/ontology/test_resource_blueprints.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, each `ConceptLevel`, and reviewed evidence metadata.
- Produces: `ConceptAttributes`, `ResourceBlueprint`, `resource_blueprint(catalog, concept_id, depth)`.

- [ ] Step 1: Write failing tests requiring every required concept/depth pair to have four-dimensional ability demand summing to 1, resource types, outcomes, assessment kinds, and estimated effort.
- [ ] Step 2: Run `uv run pytest tests/unit/ontology/test_resource_blueprints.py -q`; verify missing manifest entries fail.
- [ ] Step 3: Add chapter defaults first, then explicit concept overrides only where evidence supports them; preserve YAML ontology facts.
- [ ] Step 4: Implement manifest validation for IDs, graph version, monotonic mastery thresholds, non-empty observable outcomes, and supported resource types.
- [ ] Step 5: Add deterministic skeleton generation for all 140 x 3 pairs and regression tests for core chapters and sample CNN/RAG nodes.
- [ ] Step 6: Run graph validation plus `uv run pytest tests/unit/ontology -q` and commit `feat: define concept adaptation and resource blueprints`.

### Task 4: Deterministic Node Weight Engine

**Owner:** 课程规划 Agent（主责）+ 算法同学

**Files:**
- Create: `src/skillforge_kb/planning/adaptation.py`
- Modify: `src/skillforge_kb/planning/models.py`
- Modify: `src/skillforge_kb/planning/serialization.py`
- Modify: `src/skillforge_kb/planning/__init__.py`
- Test: `tests/unit/planning/test_adaptation.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, `LearnerProfileSnapshot`, `PathNode`, `ConceptAttributes`, `PlannerPolicy`, completed IDs.
- Produces: `NodeWeightPolicy`, `NodeAdaptationDecision`, `NodeWeightEngine.evaluate(profile, path_node, completed_ids) -> NodeAdaptationDecision`.

- [ ] Step 1: Write failing tests for zero-data, high-coding, high-theory, high-error-risk, low-confidence, and blocked nodes.
- [ ] Step 2: Run `uv run pytest tests/unit/planning/test_adaptation.py -q`; verify failures occur before implementation.
- [ ] Step 3: Implement `ability_fit`, `readiness`, `support_need`, factor contributions, stable reason codes, and bounded support intensities.
- [ ] Step 4: Ensure hard blockers force `remediation` and `intro`; preferences change only format hints; no adaptation function can reorder path nodes.
- [ ] Step 5: Include `policy_digest`, profile snapshot digest, and `adaptation_digest` in immutable output; keep `path_id` structural.
- [ ] Step 6: Add monotonicity tests: lower mastery or confidence cannot reduce support need; satisfying a blocker cannot reorder nodes; completed nodes are not recalculated.
- [ ] Step 7: Run all planning tests, Ruff, and mypy; commit `feat: add deterministic node adaptation`.

### Task 5: ResourceBrief Contract and Builder

**Owner:** 课程规划 Agent（主责）+ 资源生成 Agent 同学

**Files:**
- Create: `src/skillforge_kb/resources/models.py`
- Create: `src/skillforge_kb/resources/briefs.py`
- Modify: `src/skillforge_kb/resources/__init__.py`
- Test: `tests/unit/resources/test_models.py`
- Test: `tests/unit/resources/test_briefs.py`

**Interfaces:**
- Consumes: `PathDecision`, `OntologyCatalog`, `LearnerProfileSnapshot`, `NodeAdaptationDecision`, `EvidenceIndex`.
- Produces: `ResourceBriefBuilder.build(decision, profile, concept_id) -> ResourceBrief` and `ResourceBrief` with stable `brief_id`.

- [ ] Step 1: Write failing tests for each non-skipped node, all three depths, blocker remediation, preference hints, and evidence filters.
- [ ] Step 2: Run `uv run pytest tests/unit/resources -q`; verify missing contract/builders fail.
- [ ] Step 3: Implement frozen Pydantic models for brief, evidence filters, citation requirements, and acceptance checks.
- [ ] Step 4: Build briefs from path facts and blueprint facts without copying downstream decisions back into the profile.
- [ ] Step 5: Reject skipped/completed generation, graph/profile/policy mismatch, missing blueprint, and absent published evidence when evidence is required.
- [ ] Step 6: Add deterministic serialization and tests that resource consumers cannot override path ID, depth, sequence, or hard prerequisites.
- [ ] Step 7: Run unit suites and commit `feat: bridge course planning to resource briefs`.

### Task 6: EvidenceBundle and Resource Agent Adapter

**Owner:** 领域检索 Agent + 资源生成 Agent + 智能体搭建同学

**Files:**
- Create: `src/skillforge_kb/resources/evidence_bundle.py`
- Create: `src/skillforge_kb/resources/generator_contracts.py`
- Create: `src/skillforge_kb/agents/resource_tools.py`
- Test: `tests/unit/resources/test_evidence_bundle.py`
- Test: `tests/unit/agents/test_resource_tools.py`

**Interfaces:**
- Consumes: `ResourceBrief`, `EvidenceIndex`, and framework-neutral retrieval ports implemented later by BM25/vector/graph adapters.
- Produces: `EvidenceBundle` and a thin framework-neutral tool contract; LangChain/LangGraph wrappers are optional adapters over this contract.

- [ ] Step 1: Write failing tests for published-only evidence, query filters, missing-evidence failure, and citation completeness.
- [ ] Step 2: Implement deterministic evidence filtering and stable source ordering before adding model calls.
- [ ] Step 3: Define resource outputs for lecture, practical guide, and assessment with required citation records and acceptance statuses.
- [ ] Step 4: Add a no-LLM fake generator test; reject outputs that change brief depth/path fields or contain uncited claims.
- [ ] Step 5: Add optional LangChain Tool/LangGraph node wrappers only after core tests pass; wrappers must be retry-safe and idempotent.
- [ ] Step 6: Commit `feat: define evidence bundle and resource agent adapter`.

### Task 7: End-to-End Acceptance and Metrics

**Owner:** 算法同学 + 测试/演示同学 + 全体接口负责人

**Files:**
- Create: `tests/unit/integration/test_personalized_resource_flow.py`
- Create: `reports/generated/personalized-flow-matrix.json`
- Modify: `README.md`
- Modify: `docs/team/2026-07-29-next-phase-work-allocation.md`

**Interfaces:**
- Consumes: canonical profiles, planner, adaptation engine, evidence index, ResourceBrief, fake resource generator.
- Produces: three-profile acceptance matrix, evidence-binding rate, path invariance checks, and reproducible metrics.

- [ ] Step 1: Add zero-foundation, intermediate, and advanced profile fixtures with intentional error patterns and preferences.
- [ ] Step 2: Assert complete required-node coverage, stable path order, conservative depths, adaptation monotonicity, and brief schema validity.
- [ ] Step 3: Assert evidence binding rate, missing-evidence failures, and no downstream mutation of profiles or paths.
- [ ] Step 4: Generate the matrix report and document current gaps honestly; do not fabricate hallucination or difficulty metrics without generated-resource runs.
- [ ] Step 5: Run `uv run pytest tests/unit -q`, `uv run ruff check src tests/unit`, `uv run mypy src/skillforge_kb`, and graph validation.
- [ ] Step 6: Commit `test: verify personalized resource flow`.

## Delivery Order

Tasks 1-3 are the P0 data contracts. Task 4 can start once Task 3's concept attributes are available. Task 5 depends on Tasks 1-4. Task 6 depends on Tasks 2 and 5. Task 7 is the release gate. Neo4j integration and real model calls remain optional after the unit-level contracts are green.

## Plan Self-Review

- Every design requirement maps to Tasks 1-7: profile completeness (1), evidence governance (2), graph/resource metadata (3), dynamic adaptation (4), planner-resource bridge (5), retrieval/generation boundary (6), and acceptance evidence (7).
- No task changes path topology or writes learner-derived values into the static graph.
- All public signatures are defined before downstream use: `NodeWeightEngine.evaluate`, `ResourceBriefBuilder.build`, `EvidenceIndex.query`, and `EvidenceBundle`.
- No placeholder steps remain; each task includes concrete files, tests, commands, and commit boundaries.
