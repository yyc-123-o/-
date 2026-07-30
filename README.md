# SkillForge Knowledge Base

SkillForge Knowledge Base is a governed, bilingual evidence foundation for an AI learning system. It provides deterministic source ingestion, provenance-aware chunk candidates, review gates, and the storage contracts that will later support PostgreSQL, Qdrant, Neo4j, LangChain, and LangGraph integrations.

## Current Status

The repository currently contains:

- Domain contracts for sources, citations, evidence chunks, and retrieval packages.
- Governed source acquisition and PDF/HTML loaders.
- Deterministic normalization and pedagogical chunking.
- A read-only fusion intake pipeline for the two teammate-built knowledge bases.
- A versioned bilingual AI course ontology with chapter/section structure, prerequisite DAG validation, three depth levels, and learner-profile adaptation contracts.
- Immutable concept ability-demand and resource-blueprint catalogs covering all 140 concepts at three delivery depths.
- A deterministic node-adaptation engine with auditable support/readiness contributions that never changes path order.
- A seeded synthetic-profile generator and offline course-path evaluator with validated, reproducible metrics.
- A deterministic, idempotent answer-event baseline for updating mastery, confidence, and per-concept error patterns.
- Frozen `ResourceBrief` and `EvidenceBundle` contracts connecting course planning to evidence-bound resource generation.
- Framework-neutral lecture, practical-guide, assessment, and project output validation with a no-LLM deterministic generator for acceptance tests.
- Candidate concept-coverage reporting that never promotes unreviewed evidence into the graph.
- Parameterized, idempotent Neo4j publication for the curated course structure.
- Unit and integration tests for ingestion, governance, storage, and fusion intake.
- Versioned design documents and implementation plans under `docs/`.

The first fusion dry run processed 2,133 JSONL records without changing the input files. The records remain candidates; licensing and human review are still required before publication.

## Repository Layout

```text
src/skillforge_kb/       Core Python package and fusion intake pipeline
tests/                   Unit and service-backed integration tests
docs/                    Design specs, implementation plans, and audit summaries
data/                    Public data-handling and reproducibility notes
compose.yaml             Local PostgreSQL, Qdrant, and Neo4j services
pyproject.toml           Python dependencies and developer commands
```

## Quick Start

Requirements: Python 3.12 and `uv`.

```powershell
uv sync --frozen
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
```

The fusion CLI is read-only with respect to source directories:

```powershell
uv run skillforge-kb fusion-dry-run `
  --knowledge-root 'D:\path\to\知识库' `
  --legacy-root 'D:\path\to\processed' `
  --pilot-jsonl 'D:\path\to\ai_learning_pilot_chunks.jsonl' `
  --legacy-jsonl 'D:\path\to\index_chunks.jsonl' `
  --workspace-root 'D:\path\to\project' `
  --output-dir 'reports/generated/fusion-v1'
```

It writes deterministic inventory, source-candidate, outcome, and summary files to the chosen output directory. The output directory must be outside both input roots.

The course graph commands validate and publish only the versioned curriculum structure:

```powershell
uv run skillforge-kb graph-validate `
  --output reports/generated/graph-validation.json

uv run skillforge-kb graph-coverage `
  --pilot-jsonl 'D:\path\to\ai_learning_pilot_chunks.jsonl' `
  --output-file reports/generated/course-graph-coverage.json

uv run skillforge-kb graph-publish
```

`graph-coverage` is read-only over candidate JSONL, requires its report outside the input directory, and never publishes evidence edges. `graph-publish` validates the complete graph before opening the Neo4j connection.

The graph commands use the versioned ontology assets under `resources/ontology` by default. Pass `--course-file` and `--relations-file` to validate another explicitly versioned catalog. Neo4j integration tests and `graph-publish` require a reachable Neo4j 5 instance; Docker is not required for unit tests or static validation.

Learner profiles must be converted through the versioned `ProfileAdapter` and one-to-one legacy-ID mapping before the course planner consumes them. The adapter preserves abilities, error patterns, preferences, assessment runs, and evidence references. The production legacy mapping is intentionally empty until the team supplies human-reviewed one-to-one IDs. Raw profile exports and teammate JSONL files stay outside Git; path decisions, resource-generation hints, and agent state are not part of the graph or profile snapshot.

Structured answer events can update a copied profile through the replaceable rule baseline without an API key or external service:

```python
from skillforge_kb.assessment import AssessmentLedger, apply_assessment_event

ledger = AssessmentLedger(profile=profile_snapshot)
result = apply_assessment_event(catalog, ledger, assessment_event)
updated_profile_snapshot = result.ledger.profile
```

Policy `rule-based-assessment.v1` raises or lowers mastery from the current score, applies bounded hint and retry penalties, and increases evidence confidence toward one. Incorrect answers are classified in this order: explicit error kind, two or more hints, response time of at least 120 seconds, two or more attempts, then missed condition. `event_id` replay returns the original ledger as an explicit no-op, and individual events are not mixed into `assessment_runs`.

The updater changes only the returned learner-profile snapshot and assessment ledger. It does not call the course planner, alter the graph, reorder a path, select delivery depth, or create resource briefs. An orchestration layer may later pass the returned profile into a separate explicit replanning step. This engineering baseline is intended for offline integration and may be replaced by a reviewed BKT/IRT-style model; its outputs are not evidence of real teaching effectiveness.

The deterministic planning core converts the reviewed catalog and a canonical learner profile into a complete required-course path:

```python
from skillforge_kb.planning import CoursePlanner, DepthUpdater

decision = CoursePlanner(catalog).plan(profile_snapshot)
updated = DepthUpdater(catalog).update(
    decision,
    updated_profile_snapshot,
    completed_concept_ids={"math.linear-algebra.scalar"},
)
```

The path is generated once, keeps mastered concepts as `skipped`, and preserves its concept set, order, positions, and `path_id` during updates. Only unfinished node readiness and delivery depth may change. LangChain and LangGraph integration remains a separate adapter phase; neither framework participates in the deterministic planning algorithm.

Generate the default 60-case synthetic evaluation dataset and evaluate the course path without an API key or external service:

```powershell
uv run skillforge-kb planning-generate-synthetic `
  --output-file reports/generated/synthetic-planning-dataset.json

uv run skillforge-kb planning-evaluate `
  --dataset-file reports/generated/synthetic-planning-dataset.json `
  --output-file reports/generated/course-path-evaluation.json

uv run skillforge-kb planning-calibrate-policy `
  --dataset-file reports/generated/synthetic-planning-dataset.json `
  --output-file reports/generated/planner-policy-calibration.json
```

The dataset is stratified across beginner, intermediate, advanced, uneven, low-confidence, missing-evidence, conflicting-evidence, and boundary cohorts. The report measures prerequisite violations, required-concept coverage, skip and delivery-depth accuracy, path-order stability, conservative low-confidence handling, and mean learning/skipped node counts. These outputs are synthetic regression evidence only; they do not measure real student learning effectiveness.

The calibration command performs a bounded one-coordinate sensitivity search over confidence, skip, readiness, depth, and four-dimensional ability weights. It ranks candidates against the stored synthetic oracle but never replaces the production policy. A candidate can only be considered for promotion after expert-labelled or observed data is available and reviewed.

For each unfinished node, the planning/resource bridge computes a deterministic support decision and produces an evidence-gated generation request:

```python
from skillforge_kb.agents import FakeResourceGenerator, ResourceGenerationTool
from skillforge_kb.resources import build_evidence_bundle

adaptation = weight_engine.evaluate(profile_snapshot, path_node)
brief = brief_builder.build(decision, profile_snapshot, path_node.concept_id)
bundle = build_evidence_bundle(brief, published_evidence_index)
validated = ResourceGenerationTool().invoke(
    brief,
    bundle,
    FakeResourceGenerator(),
)
```

The fake generator is only a deterministic contract fixture. A later real resource Agent may implement the same protocol through LangChain or LangGraph, but every output must still pass the framework-neutral path, evidence, citation, and resource-type validator.

New `resource-brief.v2` requests also contain a frozen `ResourceAllocation`. It scales the reviewed 45/60/75-minute blueprint duration with the node's existing effort multiplier, rounds upward to five minutes, and assigns worked-example, guided-exercise, assessment-item, and project-checkpoint quotas from delivery depth plus support intensity. Quotas for resource types not requested by the blueprint are forced to zero.

These quota tables are versioned engineering defaults, not measured estimates of learning effectiveness. Resource-generation Agents and frontends must consume the allocation and its reason codes directly; they must not recalculate time or counts from the learner profile.

## Data Policy

Raw PDFs, source repositories, teammate JSONL files, pickle indexes, FAISS indexes, and ad hoc generated reports are intentionally excluded from Git. The deterministic acceptance fixture at `reports/generated/personalized-flow-matrix.json` is tracked as a reproducible release artifact. External data may have separate licensing, size, or reproducibility constraints. See [`data/README.md`](data/README.md) and the source manifest kept with the local data copy.

No candidate is considered publishable until its source, license, locator, normalized hash, concept labels, and human review state satisfy the governance policy.

## License

The project code is released under the repository's chosen license. External papers, teaching materials, and teammate-provided documents retain their original rights and must be checked independently before redistribution.
