# Course Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned, bilingual, course-structured AI knowledge graph with validated prerequisites, learner-profile adaptation, candidate-coverage reporting, and idempotent Neo4j publication.

**Architecture:** YAML is the editable fact source for the course topology and reviewed legacy profile-ID mapping. The `skillforge_kb.ontology` package loads and validates those assets before producing catalog queries, profile snapshots, reports, or Neo4j writes. A path algorithm, resource generation, and LangGraph are deliberately excluded.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, Typer, Neo4j Python driver, pytest, Testcontainers Neo4j, Ruff, mypy, uv.

## Global Constraints

- Use Python `>=3.12,<3.13`, Pydantic 2, strict mypy, Ruff line length 100, and the repository's `uv` workflow.
- Keep `resources/ontology/*.yaml` in Git; never add `知识库/`, `processed/`, `material/`, raw profile JSON, pickle, or FAISS files.
- YAML is the fact source. Neo4j is an idempotent derived publication surface and must never be edited manually.
- Every concept ID is lowercase ASCII matching `^[a-z0-9][a-z0-9.-]+$`; all graph and mapping versions are explicit.
- Every concept has one primary teaching section and exactly three levels: `intro`, `intermediate`, `advanced`.
- Candidate JSONL labels may affect only coverage reports. They never create graph nodes, course order, or relations.
- Never deserialize old pickle, BM25, or FAISS artifacts. Coverage reads UTF-8 JSONL through the existing iterator.
- `ProfileAdapter` is pure validation/conversion: no LLM, Neo4j write, score recomputation, or path creation.
- Legacy profile IDs require reviewed one-to-one mapping. Composite, unknown, ambiguous, deprecated, or version-mismatched IDs reject the full profile.
- Do not implement the course planner, learner-profile algorithm, LangGraph, resource generation, evidence publication, Qdrant, or frontend work.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `resources/ontology/ai_course_v1.yaml` | Course, 11 chapters, sections, 140 bilingual concepts, three levels, evidence status. |
| `resources/ontology/ai_relations_v1.yaml` | Curated prerequisite, part-of, contrast, and confusion relations. |
| `resources/ontology/legacy_profile_ids_v1.yaml` | Reviewed one-to-one legacy profile-ID mappings; initially empty. |
| `src/skillforge_kb/ontology/models.py` | Pydantic graph, relation, profile, mapping, and report contracts. |
| `src/skillforge_kb/ontology/catalog.py` | YAML loading, alias resolution, ordered graph queries, relation access. |
| `src/skillforge_kb/ontology/validation.py` | Semantic validation, cycle detection, reachability, key-path checks. |
| `src/skillforge_kb/ontology/profile.py` | Strict external-profile parsing and read-only adaptation. |
| `src/skillforge_kb/ontology/coverage.py` | Candidate JSONL coverage analysis without publication side effects. |
| `src/skillforge_kb/ontology/neo4j.py` | Parameterized idempotent Neo4j publication and prerequisite queries. |
| `src/skillforge_kb/domain/ports.py` | Read-only `ConceptGraph` protocol for later planner consumers. |
| `src/skillforge_kb/cli.py` | `graph-validate`, `graph-coverage`, and `graph-publish` commands. |
| `tests/unit/ontology/` | Model, catalog, validation, profile, coverage behavior tests. |
| `tests/integration/ontology/` | Neo4j idempotency and prerequisite-query tests. |

## Canonical Curriculum Inventory

Create exactly 11 chapters and 140 concepts. Each concept must have bilingual names, a one-sentence boundary, a primary section, `difficulty`, `required`, `review_status: reviewed`, `evidence_status`, and all three levels.

```text
chapter.01.math-foundations (12)
  math.linear-algebra.scalar, math.linear-algebra.vector, math.linear-algebra.matrix,
  math.linear-algebra.tensor, math.linear-algebra.matrix-operations,
  math.linear-algebra.matrix-multiplication, math.linear-algebra.norm,
  math.linear-algebra.eigen-decomposition, math.linear-algebra.svd,
  math.calculus.derivative-gradient, math.probability.random-variable,
  math.probability.probability-distribution

chapter.02.classical-machine-learning (16)
  ml.data.feature-label, ml.data.train-validation-test-split, ml.supervised.learning,
  ml.regression.linear-regression, ml.classification.logistic-regression,
  ml.objective.loss-function, ml.estimation.maximum-likelihood,
  ml.generalization.bias-variance, ml.generalization.overfitting,
  ml.generalization.regularization-introduction, ml.model-selection.cross-validation,
  ml.evaluation.confusion-matrix, ml.evaluation.classification-metrics,
  ml.tree.decision-tree, ml.ensemble.random-forest, ml.clustering.kmeans

chapter.03.neural-networks (12)
  dl.neuron.perceptron, dl.feedforward.mlp, dl.activation.relu,
  dl.activation.sigmoid-tanh, dl.forward-pass, dl.computation.computational-graph,
  math.calculus.chain-rule, dl.backpropagation, dl.initialization.weight-initialization,
  dl.output-layer, dl.output.softmax, dl.theory.universal-approximation

chapter.04.training-and-regularization (16)
  ml.optimization.gradient-descent, ml.optimization.stochastic-gradient-descent,
  ml.optimization.mini-batch, ml.optimization.learning-rate, ml.optimization.momentum,
  dl.optimization.adam, dl.optimization.vanishing-exploding-gradient,
  dl.regularization.l1-l2, dl.regularization.dropout, dl.regularization.early-stopping,
  dl.optimization.batch-normalization, dl.regularization.data-augmentation,
  dl.practice.hyperparameter-tuning, dl.practice.grid-random-search,
  dl.practice.training-validation-loop, dl.practice.optimization-diagnostics

chapter.05.cnn-representation (10)
  dl.vision.image-tensor, dl.cnn.convolution, dl.cnn.cross-correlation,
  dl.cnn.kernel-filter, dl.cnn.padding-stride, dl.cnn.pooling,
  dl.cnn.receptive-field, dl.cnn.architecture, dl.cnn.flatten-fully-connected,
  dl.cnn.backpropagation

chapter.06.embeddings-and-sequences (10)
  nlp.tokenization, nlp.representation.one-hot, dl.representation.embedding,
  dl.representation.cosine-similarity, nlp.sequence-modeling, nlp.rnn,
  nlp.lstm-gru, nlp.encoder-decoder, nlp.language-modeling,
  nlp.positional-information

chapter.07.transformer (16)
  llm.attention.attention, llm.attention.scaled-dot-product,
  llm.attention.self-attention, llm.attention.multi-head,
  llm.transformer.positional-encoding, llm.transformer.feed-forward,
  llm.transformer.residual-connection, llm.transformer.layer-normalization,
  llm.transformer.encoder, llm.transformer.decoder,
  llm.transformer.masked-self-attention, llm.transformer.cross-attention,
  llm.transformer.attention-complexity, llm.transformer.training,
  llm.transformer.inference, llm.transformer.attention-visualization

chapter.08.large-language-models (12)
  llm.language-modeling.autoregressive, llm.language-modeling.masked,
  llm.pretraining.bert, llm.pretraining.gpt, llm.pretraining.objectives,
  llm.pretraining.data, llm.scaling.scaling-laws, llm.prompt.in-context-learning,
  llm.prompt.prompt-engineering, llm.prompt.few-shot-learning,
  llm.inference.context-window, llm.inference.decoding

chapter.09.alignment-and-peft (12)
  llm.alignment.instruction-tuning, llm.alignment.supervised-fine-tuning,
  llm.alignment.preference-data, llm.alignment.reward-model,
  llm.alignment.rlhf, llm.alignment.ppo, llm.alignment.safety,
  llm.finetuning.parameter-efficient, llm.finetuning.lora,
  llm.finetuning.adapter-tuning, llm.finetuning.quantization, llm.finetuning.qlora

chapter.10.rag (14)
  rag.information-retrieval, rag.document-chunking, rag.dense-retrieval,
  rag.vector-index, rag.embedding-model, rag.query-expansion, rag.reranking,
  rag.hybrid-retrieval, rag.retrieval-augmented-generation,
  rag.context-construction, rag.citation-grounding, rag.retrieval-failure,
  rag.generation-failure, rag.architecture

chapter.11.rag-evaluation-and-practice (10)
  rag.evaluation, rag.evaluation.context-precision-recall, rag.evaluation.faithfulness,
  rag.evaluation.answer-relevancy, rag.evaluation.ragas, rag.evaluation.offline,
  rag.evaluation.human, rag.evaluation.ablation-study,
  rag.practice.experiment-tracking, rag.practice.end-to-end
```

The relation asset must include all atomic dependencies required by these hard paths:

```text
math.linear-algebra.vector -> math.linear-algebra.matrix
-> math.linear-algebra.matrix-multiplication -> dl.representation.embedding
-> llm.attention.scaled-dot-product -> llm.attention.self-attention
-> llm.transformer.encoder -> llm.pretraining.gpt -> rag.dense-retrieval
-> rag.retrieval-augmented-generation -> rag.evaluation.ragas

math.calculus.derivative-gradient -> math.calculus.chain-rule -> dl.backpropagation
-> ml.optimization.gradient-descent -> dl.optimization.adam -> dl.cnn.backpropagation

ml.data.feature-label -> ml.supervised.learning -> ml.regression.linear-regression
-> ml.classification.logistic-regression -> ml.evaluation.confusion-matrix
-> ml.evaluation.classification-metrics
```

## Task 1: Add Strict Ontology Models

**Files:**
- Create: `src/skillforge_kb/ontology/__init__.py`
- Create: `src/skillforge_kb/ontology/models.py`
- Create: `tests/unit/ontology/__init__.py`
- Create: `tests/unit/ontology/test_models.py`

**Interfaces:**
- Produces: `CourseDocument`, `Chapter`, `Section`, `Concept`, `ConceptLevel`, `Relation`, `RelationKind`, `LearnerProfileSnapshot`, and `ProfileIdMapping`.
- Consumed by: Tasks 2-7.

- [ ] **Step 1: Write the failing model test**

```python
import pytest
from pydantic import ValidationError

from skillforge_kb.ontology.models import Concept, ConceptLevel, DepthLevel, LocalizedName


def test_concept_requires_three_unique_depth_levels() -> None:
    levels = [
        ConceptLevel(level=DepthLevel.INTRO, learning_outcomes=["Explain vectors."],
                     mastery_threshold=0.4, assessment_kinds=["concept"]),
        ConceptLevel(level=DepthLevel.INTERMEDIATE, learning_outcomes=["Multiply matrices."],
                     mastery_threshold=0.65, assessment_kinds=["calculation"]),
        ConceptLevel(level=DepthLevel.ADVANCED, learning_outcomes=["Analyze SVD limits."],
                     mastery_threshold=0.85, assessment_kinds=["analysis"]),
    ]
    concept = Concept(
        id="math.linear-algebra.vector", names=LocalizedName(zh="向量", en="Vector"),
        aliases=[], summary="有序数值表示。", difficulty=1, required=True,
        evidence_status="coverage_gap", review_status="reviewed", levels=levels,
    )
    assert [level.level for level in concept.levels] == list(DepthLevel)


def test_concept_rejects_missing_depth_levels() -> None:
    with pytest.raises(ValidationError, match="exactly"):
        Concept.model_validate({
            "id": "math.vector", "names": {"zh": "向量", "en": "Vector"},
            "summary": "有序数值表示。", "difficulty": 1, "required": True,
            "evidence_status": "coverage_gap", "review_status": "reviewed", "levels": [],
        })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ontology/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'skillforge_kb.ontology'`.

- [ ] **Step 3: Implement the model module**

Implement string enums for three depths, five relation kinds, three evidence statuses, and three graph review statuses. Implement Pydantic models with ASCII ID patterns, 0-1 score bounds, non-empty bilingual names/outcomes, and an after-validator requiring the three unique levels in enum order. Re-export public types from `ontology/__init__.py`.

- [ ] **Step 4: Run the model tests**

Run: `uv run pytest tests/unit/ontology/test_models.py -v`

Expected: PASS with both contract tests green.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/ontology tests/unit/ontology
git commit -m "feat: add ontology domain models"
```

## Task 2: Add the Reviewed Course and Relation Assets

**Files:**
- Create: `resources/ontology/ai_course_v1.yaml`
- Create: `resources/ontology/ai_relations_v1.yaml`
- Create: `resources/ontology/legacy_profile_ids_v1.yaml`
- Create: `src/skillforge_kb/ontology/catalog.py`
- Create: `tests/unit/ontology/conftest.py`
- Create: `tests/unit/ontology/test_catalog.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: `OntologyCatalog.load(course_path, relations_path)`, `OntologyCatalog.from_documents(course, relations)`, `chapters()`, `concepts()`, `get_concept()`, `resolve_alias()`, `section_for()`, and `relations()`.

- [ ] **Step 1: Write the failing inventory test**

```python
from pathlib import Path

from skillforge_kb.ontology.catalog import OntologyCatalog


RESOURCE_ROOT = Path(__file__).parents[3] / "resources" / "ontology"


def test_course_seed_has_expected_shape() -> None:
    catalog = OntologyCatalog.load(
        RESOURCE_ROOT / "ai_course_v1.yaml", RESOURCE_ROOT / "ai_relations_v1.yaml"
    )
    assert len(catalog.chapters()) == 11
    assert len(catalog.concepts()) == 140
    assert catalog.get_concept("rag.evaluation.ragas").names.zh == "RAGAS"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ontology/test_catalog.py::test_course_seed_has_expected_shape -v`

Expected: FAIL because the assets and `OntologyCatalog` do not exist.

- [ ] **Step 3: Create the exact YAML assets and catalog**

Use the canonical inventory in this plan without adding, removing, or merging concepts. Create 2-4 ordered sections and at least two outcomes for each chapter. Add bilingual names, atomic summaries, aliases, levels, and deterministic teaching orders. Mark only current non-composite pilot labels as `candidate_supported`; mark all others `coverage_gap`. Add only human-curated relations, including the three hard paths above and reviewed contrast/confusion pairs: linear vs logistic regression, SGD vs Adam, and convolution vs cross-correlation.

Create the mapping file as:

```yaml
version: profile-id-map-v1
graph_version: ai-course-v1
mappings: []
```

Implement safe YAML loading, `from_documents(course: CourseDocument, relations: RelationDocument)`, and stable catalog ordering in `catalog.py`. Expose read-only `course_document` and `relation_document` properties for semantic-test construction.

Create the shared fixture:

```python
import pytest

from skillforge_kb.ontology.catalog import OntologyCatalog


@pytest.fixture(scope="session")
def catalog() -> OntologyCatalog:
    root = Path(__file__).parents[3] / "resources" / "ontology"
    return OntologyCatalog.load(root / "ai_course_v1.yaml", root / "ai_relations_v1.yaml")
```

The fixture module imports `Path` from `pathlib` and is available to Tasks 3-5.

- [ ] **Step 4: Run catalog tests**

Run: `uv run pytest tests/unit/ontology/test_catalog.py -v`

Expected: PASS with 11 chapters, 140 concepts, and the exact RAGAS name.

- [ ] **Step 5: Commit**

```bash
git add resources/ontology src/skillforge_kb/ontology/catalog.py tests/unit/ontology/conftest.py tests/unit/ontology/test_catalog.py
git commit -m "feat: add curated AI course graph assets"
```

## Task 3: Validate Structure, Ordering, and Learning Logic

**Files:**
- Create: `src/skillforge_kb/ontology/validation.py`
- Create: `tests/unit/ontology/test_validation.py`

**Interfaces:**
- Consumes: `OntologyCatalog`.
- Produces: `GraphValidationReport`, `GraphValidationError`, and `validate_catalog(catalog) -> GraphValidationReport`.

- [ ] **Step 1: Write failing semantic tests**

```python
import pytest

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import Relation, RelationDocument, RelationKind
from skillforge_kb.ontology.validation import GraphValidationError, validate_catalog


def test_validation_rejects_hard_prerequisite_cycle(catalog) -> None:
    cycle = Relation(
        source="rag.evaluation.ragas",
        target="math.linear-algebra.vector",
        kind=RelationKind.HARD_PREREQUISITE,
        min_mastery=0.6,
        review_status="reviewed",
    )
    cyclic_catalog = OntologyCatalog.from_documents(
        catalog.course_document,
        RelationDocument(
            version=catalog.relation_document.version,
            relations=[*catalog.relations(), cycle],
        ),
    )
    with pytest.raises(GraphValidationError, match="hard prerequisite cycle"):
        validate_catalog(cyclic_catalog)


def test_validation_accepts_key_path(catalog) -> None:
    report = validate_catalog(catalog)
    assert report.chapter_count == 11
    assert report.concept_count == 140
    assert report.key_path_ids[-1] == "rag.evaluation.ragas"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ontology/test_validation.py -v`

Expected: FAIL with missing validation module.

- [ ] **Step 3: Implement deterministic validation**

Validate duplicate IDs/aliases, contiguous chapter/section/teaching orders, one primary section per concept, three levels, dangling relations, symmetric relation duplication, hard-prerequisite cycles, hard-edge canonical-order violations, required-concept reachability, and all three key paths. The report contains version, node/edge counts, relation counts, roots, key paths, and sorted issues.

- [ ] **Step 4: Run validation tests**

Run: `uv run pytest tests/unit/ontology/test_validation.py tests/unit/ontology/test_catalog.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/ontology/validation.py tests/unit/ontology/test_validation.py
git commit -m "feat: validate course graph learning logic"
```

## Task 4: Add Learner Profile Snapshot Adaptation

**Files:**
- Create: `src/skillforge_kb/ontology/profile.py`
- Create: `tests/unit/ontology/test_profile.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, `ProfileIdMapping` records, and an external diagnostic mapping.
- Produces: `ProfileAdapter.adapt(raw: dict[str, object]) -> LearnerProfileSnapshot`.

- [ ] **Step 1: Write failing adapter tests**

```python
import pytest

from skillforge_kb.ontology.models import ProfileIdMapping
from skillforge_kb.ontology.profile import ProfileAdaptationError, ProfileAdapter


def test_adapter_rejects_unmapped_composite_legacy_id(catalog) -> None:
    adapter = ProfileAdapter(catalog, mappings=[])
    raw = {"profile_meta": {"profile_id": "p-1", "graph_version": "ai-course-v1"},
           "basic_info": {"learner_id": "learner-1"}, "dimension_1_knowledge_mastery": {
        "assessed_nodes": [{"kg_node_id": "KG-ML-001", "mastery_score": 0.88,
                              "status": "mastered", "last_tested": "2026-07-28T00:00:00Z"}]
    }}
    with pytest.raises(ProfileAdaptationError, match="KG-ML-001"):
        adapter.adapt(raw)


def test_adapter_keeps_not_assessed_score_null(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-TEST-001", concept_id="math.linear-algebra.vector",
        graph_version="ai-course-v1", reviewed_by="ontology-reviewer",
    )
    adapter = ProfileAdapter(catalog, mappings=[mapping])
    snapshot = adapter.adapt({"profile_meta": {"profile_id": "p-2", "graph_version": "ai-course-v1"},
        "basic_info": {"learner_id": "learner-2"},
        "dimension_1_knowledge_mastery": {"assessed_nodes": [
            {"kg_node_id": mapping.legacy_id, "mastery_score": None,
             "status": "unexplored", "last_tested": None}
        ]}})
    assert snapshot.knowledge_mastery[0].mastery_score is None
    assert snapshot.knowledge_mastery[0].assessment_status == "not_assessed"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ontology/test_profile.py -v`

Expected: FAIL with missing profile module.

- [ ] **Step 3: Implement pure adaptation**

Implement mapping-document loading and `ProfileAdapter`. Reject `learning_path_context`, `resource_generation_hints`, `recommendation`, and `depth_prescription`. Hash `learner_id` into `learner_ref`; do not retain grade, major, or direct identifiers. Reject numeric `unexplored` scores, all missing/non-one-to-one mappings, graph-version mismatch, and profile records that list composite IDs. Preserve only normalized mastery, ability scores with confidence/run IDs, structured error patterns/evidence IDs, and preferences.

- [ ] **Step 4: Run profile tests**

Run: `uv run pytest tests/unit/ontology/test_profile.py tests/unit/ontology/test_models.py -v`

Expected: PASS; the supplied sample shape remains rejected until its composite nodes are split.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/ontology/profile.py tests/unit/ontology/test_profile.py resources/ontology/legacy_profile_ids_v1.yaml
git commit -m "feat: add profile adapter contract"
```

## Task 5: Produce Read-Only Candidate Coverage Reports

**Files:**
- Create: `src/skillforge_kb/ontology/coverage.py`
- Create: `tests/unit/ontology/test_coverage.py`

**Interfaces:**
- Consumes: `OntologyCatalog` and pilot JSONL path.
- Produces: `CoverageReport` and `analyze_candidate_coverage(catalog, jsonl_path)`.

- [ ] **Step 1: Write failing coverage test**

```python
import json

from skillforge_kb.ontology.coverage import analyze_candidate_coverage


def test_coverage_counts_known_candidate_without_publishing(tmp_path, catalog) -> None:
    path = tmp_path / "candidate.jsonl"
    path.write_text(json.dumps({"concept_ids": ["ml.optimization.gradient-descent"]}) + "\\n")
    report = analyze_candidate_coverage(catalog, path)
    assert report.candidate_counts["ml.optimization.gradient-descent"] == 1
    assert report.published_concept_ids == ()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/ontology/test_coverage.py -v`

Expected: FAIL with missing coverage module.

- [ ] **Step 3: Implement coverage**

Use `skillforge_kb.fusion.jsonl.iter_jsonl` only. Count exact known `concept_ids`; report unknown labels, invalid JSON line numbers, per-concept counts, and sorted coverage gaps. Set `published_concept_ids` to an empty tuple. Write output atomically through a temporary sibling file and `Path.replace`.

- [ ] **Step 4: Run coverage tests**

Run: `uv run pytest tests/unit/ontology/test_coverage.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/ontology/coverage.py tests/unit/ontology/test_coverage.py
git commit -m "feat: report candidate graph coverage"
```

## Task 6: Publish and Query the Graph Through Neo4j

**Files:**
- Modify: `src/skillforge_kb/domain/ports.py`
- Create: `src/skillforge_kb/ontology/neo4j.py`
- Create: `tests/integration/ontology/conftest.py`
- Create: `tests/integration/ontology/test_neo4j.py`

**Interfaces:**
- Produces: `ConceptGraph`, `Neo4jConceptGraph.publish(catalog)`, and `Neo4jConceptGraph.prerequisites(concept_id, max_depth)`.

- [ ] **Step 1: Write failing integration test**

```python
import pytest

from skillforge_kb.ontology.neo4j import Neo4jConceptGraph


@pytest.mark.integration
def test_publish_is_idempotent_and_reads_rag_prerequisites(driver, catalog) -> None:
    graph = Neo4jConceptGraph(driver)
    graph.publish(catalog)
    graph.publish(catalog)
    assert graph.prerequisites("rag.retrieval-augmented-generation", max_depth=1) == [
        "llm.pretraining.gpt", "rag.dense-retrieval"
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/integration/ontology/test_neo4j.py -v -m integration`

Expected: FAIL because the adapter/fixture do not exist. If Docker is unavailable, retain the exact Testcontainers error and continue with unit work.

- [ ] **Step 3: Implement parameterized publication**

Add a `ConceptGraph` protocol. Create uniqueness constraints for Course, Chapter, Section, Concept, and ConceptLevel IDs. `MERGE` every node and fixed relation template by `RelationKind`; never interpolate data into Cypher. Remove only relations carrying the current graph version before inserting that version's relation set. Limit depth to 1 or 2 and return sorted concept IDs. The fixture uses `Neo4jContainer("neo4j:5.26")`, `GraphDatabase.driver`, and a `finally` close.

- [ ] **Step 4: Run service and unit verification**

Run: `uv run pytest tests/unit/ontology -v`

Expected: PASS.

Run: `uv run pytest tests/integration/ontology/test_neo4j.py -v -m integration`

Expected: PASS with Docker, or a documented environment block with no false success claim.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/domain/ports.py src/skillforge_kb/ontology/neo4j.py tests/integration/ontology
git commit -m "feat: publish course graph to neo4j"
```

## Task 7: Expose Deterministic CLI Operations

**Files:**
- Modify: `src/skillforge_kb/cli.py`
- Modify: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: `skillforge-kb graph-validate`, `graph-coverage`, and `graph-publish`.

- [ ] **Step 1: Write failing CLI test**

```python
from typer.testing import CliRunner

from skillforge_kb.cli import app


def test_graph_validate_cli_writes_report(tmp_path) -> None:
    output = tmp_path / "validation.json"
    result = CliRunner().invoke(app, ["graph-validate", "--output", str(output)])
    assert result.exit_code == 0
    assert '"concept_count": 140' in output.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py::test_graph_validate_cli_writes_report -v`

Expected: FAIL because the command is absent.

- [ ] **Step 3: Implement CLI**

Use default asset paths relative to repo root with explicit path options. `graph-validate` writes a validation report. `graph-coverage` requires candidate JSONL and writes output outside input roots. `graph-publish` validates before creating the Neo4j driver from `Settings` and publishes only curated structure. Convert semantic/filesystem errors to concise Typer failures.

- [ ] **Step 4: Run CLI tests**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/ontology -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/cli.py tests/unit/test_cli.py
git commit -m "feat: add course graph cli commands"
```

## Task 8: Verify and Document

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-27-course-knowledge-graph-design.md`

**Interfaces:** Consumes all previous tasks and produces reproducible user documentation.

- [ ] **Step 1: Verify command visibility**

Run: `uv run skillforge-kb --help`

Expected: lists `fusion-dry-run`, `graph-validate`, `graph-coverage`, and `graph-publish`. If a graph command is absent, first add a failing CLI regression test before changing implementation.

- [ ] **Step 2: Document the workflow**

Document exact validate, coverage, and publish commands. State that candidate coverage never publishes evidence, profile mapping is one-to-one, raw profile data stays out of Git, and Docker is required only for Neo4j integration/publication.

- [ ] **Step 3: Run non-service verification**

```bash
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
uv run skillforge-kb graph-validate --output reports/generated/graph-validation.json
```

Expected: unit tests, Ruff, and mypy pass; report states 11 chapters and 140 concepts.

- [ ] **Step 4: Run service verification**

Run: `uv run pytest tests/integration/ontology -v -m integration`

Expected: PASS with Docker or a recorded environment block. Never claim this test passed without an available Docker endpoint.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-07-27-course-knowledge-graph-design.md tests/unit/test_cli.py
git commit -m "docs: document course graph workflow"
```

## Plan Self-Review

- Spec coverage: Tasks 1-3 cover structure, bilingual concepts, levels, learning logic, and validation. Task 4 covers the profile boundary. Task 5 covers candidate-only evidence coverage. Tasks 6-7 cover Neo4j and reproducible commands. Task 8 verifies and documents.
- Scope control: no task implements path algorithms, LangGraph, resource generation, evidence publication, Qdrant, or frontend.
- Type consistency: `OntologyCatalog`, `Concept`, `Relation`, `ProfileAdapter`, `LearnerProfileSnapshot`, `CoverageReport`, and `Neo4jConceptGraph` retain the same names throughout.
- Data safety: no task loads legacy pickle/FAISS or commits teammate/profile raw data.


Error while loading conda entry point: anaconda-auth (No module named 'pydantic_settings')
Error while loading conda entry point: anaconda-auth (No module named 'pydantic_settings')
