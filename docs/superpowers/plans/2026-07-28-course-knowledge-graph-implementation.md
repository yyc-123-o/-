# Course Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned bilingual AI course knowledge graph with 11 ordered chapters, 140 concepts, three depth levels, acyclic prerequisites, learner-profile adaptation, and idempotent Neo4j publication.

**Architecture:** Version-controlled YAML is the only graph source of truth. A focused ontology package loads strict Pydantic contracts, validates curriculum topology before database work, adapts external learner profiles through explicit one-to-one mappings, and publishes reviewed graph structure to Neo4j with parameterized queries. Candidate evidence remains outside graph publication.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, Neo4j Python driver 5, Typer, pytest, testcontainers, Ruff, mypy, uv.

## Global Constraints

- Use Python >=3.12,<3.13 and existing dependencies only.
- Use TDD for every production behavior: prove the new test fails, implement minimally, then prove it passes.
- Keep graph assets in resources/ontology; Neo4j is derived and must be safe to rebuild.
- Do not deserialize pickle/FAISS, publish candidate evidence, or create evidence-text edges.
- Do not implement path algorithms, diagnosis algorithms, resource generation, LangChain/LangGraph, FastAPI, or frontend behavior.
- Accept learner profiles only through a one-to-one reviewed mapping. Reject unmapped, composite, ambiguous, deprecated, and version-mismatched nodes.
- Keep raw learner-profile samples and direct learner identity fields out of Git; tests use synthetic pseudonymous data.
- All writes must preserve the existing untracked .claude, final-solution Markdown, and raw learner-profile JSON files.

## File Map

| Path | Responsibility |
| --- | --- |
| resources/ontology/ai_course_v1.yaml | Course, chapter, section, concept, bilingual-name, and depth-level source data. |
| resources/ontology/ai_relations_v1.yaml | Explicit prerequisite, part-of, contrast, and confusion relations. |
| resources/ontology/legacy_profile_ids_v1.yaml | Reviewed one-to-one profile-ID mappings; empty until diagnosis nodes are split. |
| src/skillforge_kb/ontology/models.py | Pydantic graph and profile contracts. |
| src/skillforge_kb/ontology/catalog.py | YAML loading, alias resolution, canonical ordering, and lookups. |
| src/skillforge_kb/ontology/validation.py | Structural, DAG, reachability, and key-path validation. |
| src/skillforge_kb/ontology/profile.py | Read-only ProfileAdapter; no policy or path decisions. |
| src/skillforge_kb/ontology/neo4j.py | Idempotent Neo4j publication and bounded prerequisite traversal. |
| src/skillforge_kb/domain/ports.py | Read-only CourseGraph protocol for future planners. |
| src/skillforge_kb/cli.py | graph-validate, graph-coverage, and graph-publish commands. |
| tests/unit/ontology/ | Unit tests for all behavior above. |
| tests/integration/ontology/ | Neo4j idempotence and traversal tests. |

---

### Task 1: Create Graph and Profile Contracts

**Files:**
- Create: src/skillforge_kb/ontology/__init__.py
- Create: src/skillforge_kb/ontology/models.py
- Create: tests/unit/ontology/__init__.py
- Create: tests/unit/ontology/test_models.py

**Interfaces:**
- Produces CourseDocument, Chapter, Section, Concept, ConceptLevel, Relation, ProfileIdMapping, MasteryObservation, and LearnerProfileSnapshot.
- Canonical concept IDs follow ^[a-z0-9][a-z0-9.-]+$.
- Depth levels are intro, intermediate, advanced; prerequisite kinds are hard, soft.

- [ ] **Step 1: Write the failing contract test**

~~~python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.ontology.models import AssessmentStatus, ConceptLevel, MasteryObservation


def test_not_assessed_mastery_requires_null_score_and_timestamp() -> None:
    with pytest.raises(ValidationError, match="not_assessed"):
        MasteryObservation(
            concept_id="math.linear-algebra.vector",
            mastery_score=0.05,
            assessment_status=AssessmentStatus.NOT_ASSESSED,
            confidence=0.0,
            observed_at=None,
            evidence_refs=[],
        )


def test_concept_requires_exactly_three_depth_levels() -> None:
    with pytest.raises(ValidationError, match="intro"):
        ConceptLevel(
            level="expert",
            learning_outcomes=["Explain vectors"],
            mastery_threshold=0.6,
            assessment_kinds=["concept"],
        )
~~~

- [ ] **Step 2: Verify the test fails**

Run: uv run pytest tests/unit/ontology/test_models.py -v

Expected: FAIL with ModuleNotFoundError for skillforge_kb.ontology.

- [ ] **Step 3: Implement minimal Pydantic contracts**

~~~python
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class DepthLevel(StrEnum):
    INTRO = "intro"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class PrerequisiteKind(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class AssessmentStatus(StrEnum):
    ASSESSED = "assessed"
    NOT_ASSESSED = "not_assessed"


class BilingualNames(BaseModel):
    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)


class ConceptLevel(BaseModel):
    level: DepthLevel
    learning_outcomes: list[str] = Field(min_length=1)
    mastery_threshold: float = Field(ge=0, le=1)
    assessment_kinds: list[str] = Field(default_factory=list)


class MasteryObservation(BaseModel):
    concept_id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]+$")
    mastery_score: float | None = Field(default=None, ge=0, le=1)
    assessment_status: AssessmentStatus
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assessment_state(self) -> "MasteryObservation":
        if self.assessment_status is AssessmentStatus.NOT_ASSESSED:
            if self.mastery_score is not None or self.observed_at is not None:
                raise ValueError("not_assessed observations require null score and timestamp")
        elif self.mastery_score is None or self.observed_at is None:
            raise ValueError("assessed observations require score and timestamp")
        return self
~~~

Implement the remaining models in the same file:
- Course: id, bilingual title, audience, version, status.
- Chapter: id, order, bilingual title, summary, outcomes, core.
- Section: id, chapter_id, order, bilingual title, outcomes.
- Concept: id, section_id, teach_order, names, aliases, summary, difficulty, required, evidence_status, review_status, levels.
- Relation: source_id, target_id, relation_type, kind, min_mastery.
- CourseDocument: version, course, chapters, sections, concepts.
- ProfileIdMapping: legacy_id, concept_id, graph_version, reviewed_by.
- LearnerProfileSnapshot: schema_version, profile_id, learner_ref, graph_version, timestamps, assessment_runs, mastery, abilities, error patterns, preferences.

Concept validation must reject duplicate depth levels and any set other than all three DepthLevel values.

- [ ] **Step 4: Verify the test passes**

Run: uv run pytest tests/unit/ontology/test_models.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add src/skillforge_kb/ontology tests/unit/ontology
git commit -m "feat: add course graph contracts"
~~~

---

### Task 2: Build the Full Versioned Curriculum Catalog

**Files:**
- Create: resources/ontology/ai_course_v1.yaml
- Create: resources/ontology/ai_relations_v1.yaml
- Create: resources/ontology/legacy_profile_ids_v1.yaml
- Create: src/skillforge_kb/ontology/catalog.py
- Create: tests/unit/ontology/test_catalog.py

**Interfaces:**
- Consumes Task 1 models.
- Produces OntologyCatalog.load(course_path, relation_path), get_concept, resolve_alias, chapter_for, ordered_concepts, and prerequisites.
- The catalog contains exactly 11 chapters, 22 sections, 140 concepts, and 420 ConceptLevel records.

- [ ] **Step 1: Write failing catalog tests**

~~~python
from pathlib import Path

from skillforge_kb.ontology.catalog import OntologyCatalog


def test_catalog_has_fixed_course_scale_and_chapter_order() -> None:
    catalog = OntologyCatalog.load(
        Path("resources/ontology/ai_course_v1.yaml"),
        Path("resources/ontology/ai_relations_v1.yaml"),
    )
    assert [chapter.order for chapter in catalog.chapters] == list(range(1, 12))
    assert len(catalog.sections) == 22
    assert len(catalog.concepts) == 140


def test_catalog_resolves_bilingual_aliases_and_locations() -> None:
    catalog = OntologyCatalog.load(
        Path("resources/ontology/ai_course_v1.yaml"),
        Path("resources/ontology/ai_relations_v1.yaml"),
    )
    assert catalog.resolve_alias("自注意力") == "llm.transformer.self-attention"
    assert catalog.resolve_alias("RAG") == "llm.application.rag"
    assert catalog.chapter_for("llm.application.rag").order == 10
~~~

- [ ] **Step 2: Verify the tests fail**

Run: uv run pytest tests/unit/ontology/test_catalog.py -v

Expected: FAIL because the catalog module and YAML files do not exist.

- [ ] **Step 3: Author the complete catalog**

Create two sections per chapter and allocate these exact concept totals: 12, 16, 12, 16, 10, 10, 16, 12, 12, 14, 10.

Use the approved design document section 7 as the authoritative chapter sequence. The YAML must contain each of these mandatory concept IDs:

~~~text
math.linear-algebra.vector
math.linear-algebra.matrix-multiplication
math.probability.conditional-probability
math.numerical.gradient-descent
ml.regression.linear-regression
ml.classification.logistic-regression
ml.evaluation.precision-recall-f1
ml.tree.decision-tree
ml.ensemble.random-forest
dl.neural-network.mlp
dl.backpropagation.chain-rule
dl.representation.embedding
dl.optimization.adam
dl.regularization.dropout
dl.normalization.batch-normalization
dl.cnn.convolution
dl.cnn.padding-stride
dl.cnn.resnet
dl.sequence.tokenization
ml.retrieval.vector-search
llm.transformer.self-attention
llm.transformer.multi-head-attention
llm.transformer.transformer-architecture
llm.pretraining.bert
llm.pretraining.gpt
llm.prompting.in-context-learning
llm.alignment.rlhf
llm.adaptation.lora
llm.application.rag
rag.retrieval.hybrid-retrieval
rag.retrieval.reranking
rag.generation.grounded-generation
rag.citation.attribution
rag.evaluation.ragas
rag.experiment.ablation
rag.practicum.end-to-end-project
~~~

Every concept entry must include one primary section, one teach_order, bilingual names, a non-empty summary, difficulty 1-4, evidence status, review status, and all three depth levels. Use this exact shape, changing only concept-specific values:

~~~yaml
- id: math.linear-algebra.vector
  section_id: chapter.01.math-foundations.linear-algebra
  teach_order: 2
  names: {zh: 向量, en: Vector}
  aliases: [vector, 向量]
  summary: 有序数值集合，是特征、嵌入和参数表示的基本对象。
  difficulty: 1
  required: true
  evidence_status: candidate_supported
  review_status: reviewed
  levels:
    - {level: intro, learning_outcomes: [识别向量及其维度], mastery_threshold: 0.5, assessment_kinds: [concept]}
    - {level: intermediate, learning_outcomes: [完成向量运算并解释几何意义], mastery_threshold: 0.7, assessment_kinds: [calculation]}
    - {level: advanced, learning_outcomes: [将向量表示用于嵌入和相似度分析], mastery_threshold: 0.85, assessment_kinds: [application]}
~~~

Create ai_relations_v1.yaml with only the allowed relation types PREREQUISITE_OF, PART_OF, CONTRASTS_WITH, and CONFUSED_WITH. Include the following hard path exactly:

~~~yaml
- {source_id: math.linear-algebra.vector, target_id: math.linear-algebra.matrix-multiplication, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.5}
- {source_id: math.linear-algebra.matrix-multiplication, target_id: dl.representation.embedding, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.6}
- {source_id: dl.representation.embedding, target_id: llm.transformer.self-attention, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.6}
- {source_id: llm.transformer.self-attention, target_id: llm.transformer.transformer-architecture, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.7}
- {source_id: llm.transformer.transformer-architecture, target_id: llm.pretraining.gpt, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.7}
- {source_id: llm.pretraining.gpt, target_id: llm.application.rag, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.6}
- {source_id: ml.retrieval.vector-search, target_id: llm.application.rag, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.6}
- {source_id: llm.application.rag, target_id: rag.evaluation.ragas, relation_type: PREREQUISITE_OF, kind: hard, min_mastery: 0.7}
~~~

Create a valid empty mapping file:

~~~yaml
version: ai-course-v1
mappings: []
~~~

- [ ] **Step 4: Implement deterministic catalog loading**

~~~python
from pathlib import Path

import yaml

from .models import CourseDocument, Relation


class OntologyCatalog:
    def __init__(self, document: CourseDocument, relations: list[Relation]) -> None:
        self.version = document.version
        self.course = document.course
        self.chapters = sorted(document.chapters, key=lambda chapter: chapter.order)
        self.sections = {section.id: section for section in document.sections}
        self.concepts = {concept.id: concept for concept in document.concepts}
        self.relations = tuple(relations)
        self._aliases = self._build_aliases()

    @classmethod
    def load(cls, course_path: Path, relation_path: Path) -> "OntologyCatalog":
        document = CourseDocument.model_validate(
            yaml.safe_load(course_path.read_text(encoding="utf-8"))
        )
        raw_relations = yaml.safe_load(relation_path.read_text(encoding="utf-8"))
        return cls(document, [Relation.model_validate(row) for row in raw_relations["relations"]])

    def get_concept(self, concept_id: str):
        return self.concepts[concept_id]

    def prerequisites(self, concept_id: str) -> list[Relation]:
        return [relation for relation in self.relations if relation.target_id == concept_id]

    def resolve_alias(self, value: str) -> str | None:
        return self._aliases.get(value.casefold().strip())
~~~

Implement _build_aliases to reject cross-concept alias duplication. Implement chapter_for and ordered_concepts using the tuple (chapter.order, section.order, teach_order, concept.id).

- [ ] **Step 5: Verify tests pass**

Run: uv run pytest tests/unit/ontology/test_catalog.py -v

Expected: PASS.

- [ ] **Step 6: Commit**

~~~bash
git add resources/ontology src/skillforge_kb/ontology/catalog.py tests/unit/ontology/test_catalog.py
git commit -m "feat: add versioned AI course catalog"
~~~

---

### Task 3: Validate Curriculum Topology Before Publication

**Files:**
- Create: src/skillforge_kb/ontology/validation.py
- Create: tests/unit/ontology/test_validation.py

**Interfaces:**
- Consumes OntologyCatalog.
- Produces validate_catalog(catalog) and GraphValidationError.
- Must run before ProfileAdapter is used by an operator and before Neo4j driver creation.

- [ ] **Step 1: Write failing validation tests**

~~~python
import pytest

from skillforge_kb.ontology.validation import GraphValidationError, validate_catalog


def test_validator_rejects_a_hard_prerequisite_cycle(catalog_with_cycle) -> None:
    with pytest.raises(GraphValidationError, match="cycle"):
        validate_catalog(catalog_with_cycle)


def test_validator_rejects_reverse_hard_prerequisite(catalog_with_reverse_edge) -> None:
    with pytest.raises(GraphValidationError, match="canonical order"):
        validate_catalog(catalog_with_reverse_edge)


def test_validator_accepts_math_to_rag_key_path(valid_catalog) -> None:
    validate_catalog(valid_catalog)
~~~

Use tmp_path YAML fixtures for the invalid catalogs. Do not mutate production resource files in tests.

- [ ] **Step 2: Verify tests fail**

Run: uv run pytest tests/unit/ontology/test_validation.py -v

Expected: FAIL because validation.py does not exist.

- [ ] **Step 3: Implement the validator**

~~~python
from collections import defaultdict

from .catalog import OntologyCatalog
from .models import PrerequisiteKind


class GraphValidationError(ValueError):
    pass


def validate_catalog(catalog: OntologyCatalog) -> None:
    _validate_contiguous_orders(catalog)
    _validate_unique_aliases(catalog)
    _validate_primary_locations(catalog)
    _validate_relation_endpoints(catalog)
    _validate_hard_prerequisite_order(catalog)
    _validate_hard_prerequisite_dag(catalog)
    _validate_required_reachability(catalog)
    _validate_key_path(catalog)


def _validate_hard_prerequisite_dag(catalog: OntologyCatalog) -> None:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for relation in catalog.relations:
        if relation.relation_type == "PREREQUISITE_OF" and relation.kind is PrerequisiteKind.HARD:
            adjacency[relation.source_id].append(relation.target_id)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise GraphValidationError(f"hard prerequisite cycle at {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for target_id in adjacency[node_id]:
            visit(target_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for concept_id in catalog.concepts:
        visit(concept_id)
~~~

Validate exact contiguous chapter and section orders, one primary section per concept, relation endpoint existence, a strictly earlier canonical location for each hard prerequisite, no relation duplicate, all required concepts reachable from root concepts, and the eight edges listed in Task 2.

- [ ] **Step 4: Verify tests pass**

Run: uv run pytest tests/unit/ontology/test_validation.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add src/skillforge_kb/ontology/validation.py tests/unit/ontology/test_validation.py
git commit -m "feat: validate course graph topology"
~~~

---

### Task 4: Add the Read-only Learner Profile Adapter

**Files:**
- Create: src/skillforge_kb/ontology/profile.py
- Create: tests/unit/ontology/test_profile.py

**Interfaces:**
- Consumes OntologyCatalog, ProfileIdMapping, and an external JSON-like mapping.
- Produces ProfileAdapter.adapt(raw) -> LearnerProfileSnapshot.
- Raises ProfileAdaptationError on unknown, composite, or non-versioned IDs, null-state errors, direct identity leakage, or derived path/resource fields.

- [ ] **Step 1: Write failing adapter tests**

~~~python
import pytest

from skillforge_kb.ontology.profile import ProfileAdaptationError, ProfileAdapter


def test_adapter_rejects_composite_legacy_node(catalog, empty_mappings) -> None:
    raw = {
        "profile_meta": {"profile_id": "profile-1", "generated_at": "2026-07-28T00:00:00Z"},
        "basic_info": {"learner_id": "LRN-1"},
        "dimension_1_knowledge_mastery": {
            "assessed_nodes": [
                {"kg_node_id": "KG-ML-001", "mastery_score": 0.88, "last_tested": "2026-07-28T00:00:00Z"}
            ]
        },
    }
    with pytest.raises(ProfileAdaptationError, match="KG-ML-001"):
        ProfileAdapter(catalog, empty_mappings).adapt(raw)


def test_adapter_converts_unexplored_to_not_assessed(catalog, mappings, raw_unexplored) -> None:
    snapshot = ProfileAdapter(catalog, mappings).adapt(raw_unexplored)
    observation = snapshot.knowledge_mastery[0]
    assert observation.assessment_status.value == "not_assessed"
    assert observation.mastery_score is None


def test_adapter_rejects_path_and_resource_fields(catalog, mappings, raw_with_path) -> None:
    with pytest.raises(ProfileAdaptationError, match="learning_path_context"):
        ProfileAdapter(catalog, mappings).adapt(raw_with_path)
~~~

- [ ] **Step 2: Verify tests fail**

Run: uv run pytest tests/unit/ontology/test_profile.py -v

Expected: FAIL because profile.py does not exist.

- [ ] **Step 3: Implement adapter behavior**

~~~python
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from skillforge_kb.ingestion.normalize import sha256_text

from .catalog import OntologyCatalog
from .models import AssessmentStatus, LearnerProfileSnapshot, MasteryObservation, ProfileIdMapping


class ProfileAdaptationError(ValueError):
    pass


class ProfileAdapter:
    def __init__(self, catalog: OntologyCatalog, mappings: list[ProfileIdMapping]) -> None:
        self._catalog = catalog
        self._mappings = {mapping.legacy_id: mapping for mapping in mappings}
        if len(self._mappings) != len(mappings):
            raise ProfileAdaptationError("duplicate legacy profile mapping")

    def adapt(self, raw: Mapping[str, Any]) -> LearnerProfileSnapshot:
        self._reject_derived_fields(raw)
        meta = self._require_mapping(raw, "profile_meta")
        basic = self._require_mapping(raw, "basic_info")
        return LearnerProfileSnapshot(
            schema_version="learner-profile.v1",
            profile_id=str(meta["profile_id"]),
            learner_ref=f"learner-{sha256_text(str(basic['learner_id']))[:20]}",
            graph_version=self._catalog.version,
            observed_at=self._parse_datetime(meta["generated_at"]),
            generated_at=self._parse_datetime(meta["generated_at"]),
            assessment_runs=[str(meta.get("generated_by", "diagnostic-unknown"))],
            knowledge_mastery=self._adapt_mastery(raw),
            abilities={},
            error_patterns=[],
            preferences={},
        )
~~~

Implement _adapt_mastery to require an exact mapping and an extant concept for every source node, convert source status unexplored to NOT_ASSESSED with score None, and reject all unmapped data. Implement _reject_derived_fields for learning_path_context, resource_generation_hints, prior_chapter_performance, recommendation, and depth_prescription. Preserve no direct learner identifier, grade, major, target project, or free-text claim in the result.

- [ ] **Step 4: Verify tests pass**

Run: uv run pytest tests/unit/ontology/test_profile.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add src/skillforge_kb/ontology/profile.py tests/unit/ontology/test_profile.py resources/ontology/legacy_profile_ids_v1.yaml
git commit -m "feat: adapt learner profiles to course graph"
~~~

---

### Task 5: Publish Validated Graphs to Neo4j

**Files:**
- Create: src/skillforge_kb/ontology/neo4j.py
- Modify: src/skillforge_kb/domain/ports.py
- Create: tests/integration/ontology/__init__.py
- Create: tests/integration/ontology/conftest.py
- Create: tests/integration/ontology/test_neo4j.py

**Interfaces:**
- Produces Neo4jCourseGraph.publish(catalog) and prerequisites(concept_id, max_depth).
- Adds CourseGraph protocol for future read-only planners.

- [ ] **Step 1: Write failing integration test**

~~~python
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.neo4j import Neo4jCourseGraph
from skillforge_kb.ontology.validation import validate_catalog


@pytest.mark.integration
def test_publish_is_idempotent_and_expands_rag_prerequisites(neo4j_uri: str) -> None:
    catalog = OntologyCatalog.load(
        Path("resources/ontology/ai_course_v1.yaml"),
        Path("resources/ontology/ai_relations_v1.yaml"),
    )
    validate_catalog(catalog)
    driver = GraphDatabase.driver(neo4j_uri, auth=("neo4j", "password"))
    graph = Neo4jCourseGraph(driver)
    graph.publish(catalog)
    graph.publish(catalog)
    assert "llm.transformer.self-attention" in graph.prerequisites("llm.application.rag", 2)
    driver.close()
~~~

- [ ] **Step 2: Verify integration test fails**

Run: uv run pytest tests/integration/ontology/test_neo4j.py -v -m integration

Expected: FAIL because Neo4jCourseGraph does not exist, or record the exact Docker/Testcontainers environment block.

- [ ] **Step 3: Implement safe idempotent publication**

~~~python
from neo4j import Driver

from .catalog import OntologyCatalog


class Neo4jCourseGraph:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def publish(self, catalog: OntologyCatalog) -> None:
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (n:Concept) REQUIRE n.id IS UNIQUE"
            ).consume()
            session.run(
                "UNWIND $rows AS row MERGE (n:Concept {id: row.id}) "
                "SET n.zh = row.names.zh, n.en = row.names.en, "
                "n.difficulty = row.difficulty, n.required = row.required, "
                "n.graph_version = $version",
                rows=[concept.model_dump(mode="json") for concept in catalog.concepts.values()],
                version=catalog.version,
            ).consume()
~~~

Create unique constraints for Course, Chapter, Section, Concept, and ConceptLevel IDs. Publish all hierarchy and concept relations using parameterized UNWIND and MERGE queries. Publish only HAS_CHAPTER, HAS_SECTION, TEACHES, HAS_LEVEL, PREREQUISITE_OF, PART_OF, CONTRASTS_WITH, and CONFUSED_WITH. Restrict traversal depth to 1 or 2 and relation type to PREREQUISITE_OF.

Append this port:

~~~python
class CourseGraph(Protocol):
    def prerequisites(self, concept_id: str, max_depth: int = 2) -> list[str]: ...
~~~

- [ ] **Step 4: Verify integration and typing**

Run: uv run pytest tests/integration/ontology/test_neo4j.py -v -m integration

Expected: PASS with Docker; otherwise report the environment block without claiming success.

Run: uv run mypy src/skillforge_kb/ontology src/skillforge_kb/domain/ports.py

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add src/skillforge_kb/ontology/neo4j.py src/skillforge_kb/domain/ports.py tests/integration/ontology
git commit -m "feat: publish course graph to neo4j"
~~~

---

### Task 6: Add Graph CLI Commands and Release Verification

**Files:**
- Modify: src/skillforge_kb/cli.py
- Create: tests/unit/ontology/test_cli.py
- Create: tests/unit/ontology/test_report.py
- Modify: README.md
- Create: docs/reports/course-graph-v1-validation.json

**Interfaces:**
- Produces graph-validate, graph-coverage, and graph-publish commands.
- Produces a public structural report with no learner identity, raw evidence text, or local absolute paths.

- [ ] **Step 1: Write failing CLI and report tests**

~~~python
import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb.cli import app


def test_graph_validate_reports_catalog_scale() -> None:
    result = CliRunner().invoke(
        app,
        [
            "graph-validate",
            "--course-file", str(Path("resources/ontology/ai_course_v1.yaml")),
            "--relations-file", str(Path("resources/ontology/ai_relations_v1.yaml")),
        ],
    )
    assert result.exit_code == 0
    assert "11 chapters" in result.stdout
    assert "140 concepts" in result.stdout


def test_validation_report_is_structural_only() -> None:
    report = json.loads(Path("docs/reports/course-graph-v1-validation.json").read_text(encoding="utf-8"))
    assert report["chapter_count"] == 11
    assert report["concept_count"] == 140
    assert report["concept_level_count"] == 420
    assert report["hard_prerequisite_cycles"] == 0
    assert "learner_id" not in json.dumps(report)
~~~

- [ ] **Step 2: Verify tests fail**

Run: uv run pytest tests/unit/ontology/test_cli.py tests/unit/ontology/test_report.py -v

Expected: FAIL because commands and report do not exist.

- [ ] **Step 3: Implement commands and report**

Add this command before graph-publish:

~~~python
@app.command("graph-validate")
def graph_validate(
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    relations_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    catalog = OntologyCatalog.load(course_file, relations_file)
    validate_catalog(catalog)
    typer.echo(f"Validated {len(catalog.chapters)} chapters and {len(catalog.concepts)} concepts")
~~~

Implement graph-coverage as a read-only candidate-label report with pilot JSONL input and an output path outside raw roots. Implement graph-publish so it validates before creating GraphDatabase.driver. Write this exact report shape with structural values generated from the catalog:

~~~json
{
  "graph_version": "ai-course-v1",
  "chapter_count": 11,
  "section_count": 22,
  "concept_count": 140,
  "concept_level_count": 420,
  "hard_prerequisite_cycles": 0,
  "required_concepts_unreachable": 0,
  "profile_mapping_count": 0,
  "candidate_evidence_edges_published": 0
}
~~~

Document the exact commands in README.md:

~~~powershell
uv run skillforge-kb graph-validate --course-file resources/ontology/ai_course_v1.yaml --relations-file resources/ontology/ai_relations_v1.yaml
uv run skillforge-kb graph-coverage --course-file resources/ontology/ai_course_v1.yaml --relations-file resources/ontology/ai_relations_v1.yaml --pilot-jsonl 'D:\path\to\ai_learning_pilot_chunks.jsonl' --workspace-root 'D:\path\to\project' --output-file reports/generated/course-graph-coverage.json
uv run skillforge-kb graph-publish --course-file resources/ontology/ai_course_v1.yaml --relations-file resources/ontology/ai_relations_v1.yaml
~~~

- [ ] **Step 4: Verify all quality gates**

Run: uv run pytest tests/unit -q

Expected: PASS.

Run: uv run ruff check src tests

Expected: PASS.

Run: uv run mypy src/skillforge_kb

Expected: PASS.

Run: uv run pytest tests/integration/ontology/test_neo4j.py -v -m integration

Expected: PASS with Docker, or an explicitly recorded Docker/Testcontainers block.

- [ ] **Step 5: Commit**

~~~bash
git add src/skillforge_kb/cli.py tests/unit/ontology README.md docs/reports/course-graph-v1-validation.json
git commit -m "feat: expose and verify course graph"
~~~

## Plan Self-Review

### Spec coverage

- Eleven chapters, bilingual concepts, three depth levels, and source-controlled YAML: Tasks 1-2.
- Acyclic hard prerequisites, canonical ordering, reachability, and the math-to-RAG path: Task 3.
- One-to-one profile mapping, composite rejection, null unknowns, privacy, and separation from paths/resources: Task 4.
- Parameterized idempotent Neo4j publication and bounded prerequisite traversal: Task 5.
- CLI operation, coverage reporting, documentation, and full quality gates: Task 6.

### Placeholder scan

The plan has no deferred implementation markers. The empty legacy mapping file is intentional: the supplied profile uses composite nodes and must be rejected until the diagnosis group supplies split, reviewed one-to-one identifiers.

### Type consistency

OntologyCatalog is the only graph input to validation, profile adaptation, Neo4j publication, and CLI commands. Concept.id is the identifier used in YAML, relations, profiles, ports, and database nodes. ProfileAdapter never creates PathDecision or ResourceBrief.
