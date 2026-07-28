# Course Planning Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic course-planning core that converts the reviewed course ontology and a learner profile snapshot into a complete, stable, explainable required-concept path, then safely updates only unfinished node state and depth.

**Architecture:** A new `skillforge_kb.planning` package owns policy and decision contracts, stable topological ordering, canonical path identifiers, initial planning, and immutable-path updates. The package consumes `OntologyCatalog` and `LearnerProfileSnapshot` in memory; it performs no I/O and has no Neo4j, LangChain, LangGraph, model, or network dependency.

**Tech Stack:** Python 3.12, Pydantic 2, hashlib/json standard library, pytest, Ruff, mypy, uv.

## Global Constraints

- Default scope is every `Concept.required=true` concept; target-specific subpaths are excluded.
- A path keeps mastered concepts as `skipped`; it never removes them.
- Initial ordering uses only `hard_prerequisite` edges and the stable course-position tie-breaker.
- `planner-policy.v1` uses the exact thresholds and weights from the approved design.
- Missing or low-confidence evidence is conservative: no fabricated medium ability and no depth above `intro`.
- An unmet hard prerequisite prevents `intermediate` and `advanced` and records a stable blocker reason.
- An update must preserve `path_id`, node identities, sequence, chapter, section, and every already-finished node depth.
- Planner unit tests must not require Docker, Neo4j, network access, or a language model.
- Do not modify or commit `.claude/`, `SkillForge-MA-最终方案.md`, or `学情画像输出-示例.json`.

---

### Task 1: Planning Contracts and Canonical Path Identity

**Files:**
- Create: `src/skillforge_kb/planning/__init__.py`
- Create: `src/skillforge_kb/planning/models.py`
- Create: `src/skillforge_kb/planning/serialization.py`
- Create: `tests/unit/planning/__init__.py`
- Create: `tests/unit/planning/test_models.py`
- Create: `tests/unit/planning/test_serialization.py`

**Interfaces:**
- Consumes: `DepthLevel` and graph ID patterns from `skillforge_kb.ontology.models`.
- Produces: `AbilityWeights`, `PlannerPolicy`, `PathStatus`, `ReasonCode`, `PathNode`, `PathDecision`, and `build_path_id(profile_id, graph_version, policy_version, concept_ids, policy_digest)`.

- [ ] **Step 1: Write failing policy and path-model tests**

```python
from pydantic import ValidationError
import pytest

from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.planning.models import PathNode, PathStatus, PlannerPolicy


def test_default_policy_uses_reviewed_v1_thresholds() -> None:
    policy = PlannerPolicy()
    assert policy.version == "planner-policy.v1"
    assert policy.minimum_confidence == 0.60
    assert policy.skip_mastery == 0.85
    assert policy.skip_confidence == 0.80
    assert sum(policy.ability_weights.values()) == pytest.approx(1.0)


def test_policy_rejects_invalid_weight_sums() -> None:
    with pytest.raises(ValidationError, match="ability weights must sum to 1"):
        PlannerPolicy(ability_weights={"coding_ability": 1.0})


def test_skipped_node_requires_null_depth() -> None:
    with pytest.raises(ValidationError, match="skipped nodes must not have a delivery depth"):
        PathNode(
            concept_id="math.linear-algebra.vector",
            chapter_id="chapter.01.math-foundations",
            section_id="section.01.linear-algebra",
            sequence=1,
            status=PathStatus.SKIPPED,
            delivery_depth=DepthLevel.INTRO,
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/unit/planning/test_models.py -q`

Expected: collection fails because `skillforge_kb.planning` does not exist.

- [ ] **Step 3: Implement the minimal Pydantic contracts**

Define: 

```python
class PathStatus(StrEnum):
    SKIPPED = "skipped"
    AVAILABLE = "available"
    BLOCKED = "blocked"
    PENDING = "pending"
    COMPLETED = "completed"


class ReasonCode(StrEnum):
    MASTERY_SKIP_THRESHOLD_MET = "mastery_skip_threshold_met"
    MASTERY_MISSING = "mastery_missing"
    MASTERY_LOW_CONFIDENCE = "mastery_low_confidence"
    ABILITY_INCOMPLETE = "ability_incomplete"
    ABILITY_LOW_CONFIDENCE = "ability_low_confidence"
    HARD_PREREQUISITE_UNASSESSED = "hard_prerequisite_unassessed"
    HARD_PREREQUISITE_LOW_CONFIDENCE = "hard_prerequisite_low_confidence"
    HARD_PREREQUISITE_BELOW_THRESHOLD = "hard_prerequisite_below_threshold"
    READY_FOR_INTRO = "ready_for_intro"
    READY_FOR_INTERMEDIATE = "ready_for_intermediate"
    READY_FOR_ADVANCED = "ready_for_advanced"
```

Implement the exact approved defaults in `PlannerPolicy` and a frozen nested `AbilityWeights` model. Validate both weight sums with `math.isclose(..., abs_tol=1e-9)`, ordered depth thresholds, continuous `sequence >= 1`, unique concepts, valid status/depth combinations, and unique reason/blocker lists. `PathDecision.generated_at` is `datetime | None` so planning remains deterministic when the profile has no generation time.

- [ ] **Step 4: Verify model tests are GREEN**

Run: `uv run pytest tests/unit/planning/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Write the failing canonical ID test**

```python
from skillforge_kb.planning.models import PlannerPolicy
from skillforge_kb.planning.serialization import build_path_id, build_policy_digest


def test_path_id_is_stable_and_order_sensitive() -> None:
    policy_digest = build_policy_digest(PlannerPolicy())
    first = build_path_id(
        "profile-1", "ai-course-v1", "planner-policy.v1", ["a", "b"], policy_digest
    )
    repeated = build_path_id(
        "profile-1", "ai-course-v1", "planner-policy.v1", ["a", "b"], policy_digest
    )
    reversed_id = build_path_id(
        "profile-1", "ai-course-v1", "planner-policy.v1", ["b", "a"], policy_digest
    )
    assert first == repeated
    assert first != reversed_id
    assert first.startswith("path_")
```

- [ ] **Step 6: Verify the ID test is RED, implement it, and verify GREEN**

Run: `uv run pytest tests/unit/planning/test_serialization.py -q`

Expected before implementation: import or attribute failure.

Implement UTF-8 JSON serialization with `sort_keys=True`, `ensure_ascii=True`, and compact separators; hash it with SHA-256 and prefix `path_`. Re-run the test and expect PASS.

- [ ] **Step 7: Export the public contracts and run local quality checks**

Run:

```powershell
uv run pytest tests/unit/planning/test_models.py tests/unit/planning/test_serialization.py -q
uv run ruff check src/skillforge_kb/planning tests/unit/planning
uv run mypy src/skillforge_kb/planning
```

Expected: all pass.

- [ ] **Step 8: Commit**

```powershell
git add src/skillforge_kb/planning tests/unit/planning
git commit -m "feat: define course planning contracts"
```

---

### Task 2: Stable Required-Course Topological Ordering

**Files:**
- Create: `src/skillforge_kb/planning/ordering.py`
- Create: `tests/unit/planning/conftest.py`
- Create: `tests/unit/planning/test_ordering.py`
- Modify: `src/skillforge_kb/planning/__init__.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, its `course_document.teaches`, sections, chapters, concepts, and `RelationKind.HARD_PREREQUISITE`.
- Produces: immutable `CoursePosition` and `stable_required_concept_ids(catalog) -> list[str]`, plus `course_positions(catalog) -> dict[str, CoursePosition]`.

- [ ] **Step 1: Add the shared real-catalog fixture**

```python
from pathlib import Path
import pytest
from skillforge_kb.ontology.catalog import OntologyCatalog


@pytest.fixture(scope="session")
def catalog() -> OntologyCatalog:
    root = Path(__file__).parents[3] / "resources" / "ontology"
    return OntologyCatalog.load(root / "ai_course_v1.yaml", root / "ai_relations_v1.yaml")
```

- [ ] **Step 2: Write failing ordering tests**

```python
from skillforge_kb.ontology.models import RelationKind
from skillforge_kb.planning.ordering import stable_required_concept_ids


def test_required_course_order_covers_every_required_concept(catalog) -> None:
    ordered = stable_required_concept_ids(catalog)
    required = {item.id for item in catalog.concepts() if item.required}
    assert len(ordered) == len(required)
    assert set(ordered) == required


def test_every_required_hard_prerequisite_precedes_its_target(catalog) -> None:
    ordered = stable_required_concept_ids(catalog)
    index = {concept_id: position for position, concept_id in enumerate(ordered)}
    for edge in catalog.relations(RelationKind.HARD_PREREQUISITE):
        if edge.source in index and edge.target in index:
            assert index[edge.source] < index[edge.target]


def test_ordering_is_deterministic(catalog) -> None:
    assert stable_required_concept_ids(catalog) == stable_required_concept_ids(catalog)
```

- [ ] **Step 3: Run and verify RED**

Run: `uv run pytest tests/unit/planning/test_ordering.py -q`

Expected: import failure because `ordering.py` is absent.

- [ ] **Step 4: Implement stable Kahn sorting**

Create a frozen `CoursePosition(chapter_order, section_order, teaching_order, chapter_id, section_id)`. Build the required-concept subgraph from hard edges. Use `heapq` with key `(chapter_order, section_order, teaching_order, concept_id)`. Validate the catalog first, reject a residual cycle with `PlanningError`, and return exactly the required IDs.

- [ ] **Step 5: Run ordering tests and package quality checks**

```powershell
uv run pytest tests/unit/planning/test_ordering.py -q
uv run ruff check src/skillforge_kb/planning tests/unit/planning
uv run mypy src/skillforge_kb/planning
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/skillforge_kb/planning tests/unit/planning
git commit -m "feat: order required course concepts"
```

---

### Task 3: Initial Deterministic Course Planning

**Files:**
- Create: `src/skillforge_kb/planning/planner.py`
- Create: `tests/unit/planning/test_planner.py`
- Modify: `src/skillforge_kb/planning/__init__.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, `LearnerProfileSnapshot`, `PlannerPolicy`, stable ordering, and canonical `build_path_id`.
- Produces: `PlanningError` and `CoursePlanner(catalog, policy).plan(profile) -> PathDecision`.

- [ ] **Step 1: Write a failing zero-data conservative-planning test**

```python
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.planning.planner import CoursePlanner


def profile_without_assessments(catalog) -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-zero",
        learner_ref="0" * 64,
        graph_version=catalog.course_document.version,
    )


def test_zero_data_profile_gets_complete_conservative_path(catalog) -> None:
    decision = CoursePlanner(catalog).plan(profile_without_assessments(catalog))
    required_count = sum(item.required for item in catalog.concepts())
    assert len(decision.nodes) == required_count
    assert all(node.delivery_depth is None or node.delivery_depth.value == "intro" for node in decision.nodes)
    assert sum(node.status is PathStatus.AVAILABLE for node in decision.nodes) == 1
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/planning/test_planner.py::test_zero_data_profile_gets_complete_conservative_path -q`

Expected: import failure because `planner.py` is absent.

- [ ] **Step 3: Implement profile indexing and initial conservative nodes**

Validate graph and profile versions. Build a unique mastery index and reject duplicate/unknown IDs with `PlanningError`. For each required concept, attach its stable position and sorted direct hard-prerequisite IDs. Initially compute missing mastery/ability as `intro`, then assign one `available` node and all later unblocked nodes `pending`.

- [ ] **Step 4: Verify the first planner test is GREEN**

Run: `uv run pytest tests/unit/planning/test_planner.py::test_zero_data_profile_gets_complete_conservative_path -q`

Expected: PASS.

- [ ] **Step 5: Add failing skip, readiness, and blocker tests**

Use small copied profile snapshots against the real catalog:

```python
def test_high_confidence_mastery_keeps_node_as_skipped(catalog) -> None:
    profile = profile_with_mastery(
        catalog, "math.linear-algebra.scalar", mastery=0.90, confidence=0.90
    )
    decision = CoursePlanner(catalog).plan(profile)
    node = node_for(decision, "math.linear-algebra.scalar")
    assert node.status is PathStatus.SKIPPED
    assert node.delivery_depth is None


def test_complete_high_readiness_can_select_advanced(catalog) -> None:
    profile = profile_with_mastery_and_abilities(
        catalog, "math.linear-algebra.scalar", mastery=0.90, ability=0.90, confidence=0.90
    )
    node = node_for(CoursePlanner(catalog).plan(profile), "math.linear-algebra.scalar")
    assert node.delivery_depth is DepthLevel.ADVANCED


def test_unassessed_hard_prerequisite_blocks_advanced_depth(catalog) -> None:
    profile = profile_with_mastery_and_abilities(
        catalog, "math.linear-algebra.vector", mastery=0.90, ability=0.90, confidence=0.90
    )
    node = node_for(CoursePlanner(catalog).plan(profile), "math.linear-algebra.vector")
    assert node.status is PathStatus.BLOCKED
    assert node.delivery_depth is DepthLevel.INTRO
    assert node.blocking_prerequisite_ids == ["math.linear-algebra.scalar"]
```

- [ ] **Step 6: Run the new tests and verify RED for missing decision rules**

Run: `uv run pytest tests/unit/planning/test_planner.py -q`

Expected: the conservative test passes while skip/readiness/blocker assertions fail.

- [ ] **Step 7: Implement the approved decision rules**

Implement exact threshold comparisons, four-dimensional weighted ability with confidence checks, readiness calculation, direct hard-edge `min_mastery` checks, stable reason codes, and status assignment. A skipped prerequisite still needs a mastery score meeting the relation threshold. Use decimal-free ordinary floats and compare only against the policy thresholds; do not round readiness before selection.

- [ ] **Step 8: Add validation and determinism tests**

Test rejection of profile/graph version mismatch, duplicate mastery entries, unknown concepts, and identical semantic output for repeated planning. Assert `path_id` and ordered nodes match exactly.

- [ ] **Step 9: Run all planner tests and local quality checks**

```powershell
uv run pytest tests/unit/planning/test_planner.py -q
uv run ruff check src/skillforge_kb/planning tests/unit/planning
uv run mypy src/skillforge_kb/planning
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add src/skillforge_kb/planning tests/unit/planning
git commit -m "feat: generate deterministic course paths"
```

---

### Task 4: Immutable-Path Chapter Update

**Files:**
- Create: `src/skillforge_kb/planning/updater.py`
- Create: `tests/unit/planning/test_updater.py`
- Modify: `src/skillforge_kb/planning/__init__.py`

**Interfaces:**
- Consumes: `CoursePlanner`, an existing `PathDecision`, a new `LearnerProfileSnapshot`, and `completed_concept_ids: set[str]`.
- Produces: `DepthUpdater(catalog, policy).update(existing, profile, completed_concept_ids) -> PathDecision`.

- [ ] **Step 1: Write the failing path-invariance update test**

```python
def test_update_preserves_identity_order_and_completed_depth(catalog) -> None:
    planner = CoursePlanner(catalog)
    existing = planner.plan(intermediate_profile(catalog))
    completed_id = next(
        node.concept_id for node in existing.nodes if node.delivery_depth is not None
    )
    original = node_for(existing, completed_id)

    updated = DepthUpdater(catalog).update(
        existing, advanced_profile(catalog), {completed_id}
    )

    assert updated.path_id == existing.path_id
    assert [node.concept_id for node in updated.nodes] == [
        node.concept_id for node in existing.nodes
    ]
    completed = node_for(updated, completed_id)
    assert completed.status is PathStatus.COMPLETED
    assert completed.delivery_depth == original.delivery_depth
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/planning/test_updater.py -q`

Expected: import failure because `updater.py` is absent.

- [ ] **Step 3: Implement update validation and recomputation**

Verify profile ID, graph version, and policy version; verify all completion IDs exist; recompute a fresh decision using `CoursePlanner`; verify the fresh ordered concept IDs and course positions equal the existing decision. Merge only unfinished nodes from the fresh decision. Preserve initial skipped nodes; preserve every previously completed node and its depth; mark newly completed nodes while preserving their existing depth. Re-run the same single-available-node status pass after merging.

- [ ] **Step 4: Add failing identity/version/tampering tests**

Test that update raises `PlanningError` for another profile, another graph version, another policy version, an unknown completed concept, and a modified existing node order or position.

- [ ] **Step 5: Run update tests and package checks**

```powershell
uv run pytest tests/unit/planning/test_updater.py -q
uv run ruff check src/skillforge_kb/planning tests/unit/planning
uv run mypy src/skillforge_kb/planning
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/skillforge_kb/planning tests/unit/planning
git commit -m "feat: update unfinished course path nodes"
```

---

### Task 5: Three-Profile Acceptance Matrix and Documentation

**Files:**
- Create: `tests/unit/planning/test_scenarios.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-28-course-planning-core-design.md`

**Interfaces:**
- Consumes: the public `skillforge_kb.planning` API.
- Produces: executable acceptance evidence for zero-foundation, intermediate, and advanced learner profiles and documented integration boundaries.

- [ ] **Step 1: Write the three-profile acceptance tests**

Create deterministic snapshot factories with all four ability dimensions and reviewed mastery records. Assert:

```python
@pytest.mark.parametrize("profile_factory", [zero_profile, intermediate_profile, advanced_profile])
def test_every_profile_covers_all_required_concepts(catalog, profile_factory) -> None:
    decision = CoursePlanner(catalog).plan(profile_factory(catalog))
    required = {item.id for item in catalog.concepts() if item.required}
    assert {node.concept_id for node in decision.nodes} == required


def test_intermediate_profile_keeps_mastered_nodes_as_skipped(catalog) -> None:
    decision = CoursePlanner(catalog).plan(intermediate_profile(catalog))
    assert any(node.status is PathStatus.SKIPPED for node in decision.nodes)


def test_advanced_profile_can_reach_advanced_without_order_violations(catalog) -> None:
    decision = CoursePlanner(catalog).plan(advanced_profile(catalog))
    assert any(node.delivery_depth is DepthLevel.ADVANCED for node in decision.nodes)
    assert_hard_prerequisite_order(catalog, decision)
```

- [ ] **Step 2: Run the acceptance tests and fix only contract defects**

Run: `uv run pytest tests/unit/planning/test_scenarios.py -q`

Expected: PASS. If a test exposes a defect, first add the smallest focused regression test to the owning Task 1-4 test file, then fix the owning module. Do not weaken the scenario assertion.

- [ ] **Step 3: Document the pure planner boundary**

Update README with a concise Python example:

```python
from skillforge_kb.planning import CoursePlanner

decision = CoursePlanner(catalog).plan(profile_snapshot)
```

State explicitly that the path covers every required concept, is generated once, keeps skipped nodes, and may only be depth-updated through `DepthUpdater`. State that LangChain/LangGraph integration remains the next adapter phase. Change the design status to implemented only after all checks pass.

- [ ] **Step 4: Run the full non-service verification**

```powershell
uv run pytest tests/unit/planning -q
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
uv run skillforge-kb graph-validate --output reports/generated/graph-validation.json
git diff --check
```

Expected: all tests and static checks pass; graph validation reports 11 chapters, 27 sections, and 140 concepts; the ontology YAML files remain unchanged.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/superpowers/specs/2026-07-28-course-planning-core-design.md tests/unit/planning
git commit -m "docs: verify deterministic course planning"
```

---

## Plan Self-Review

- Spec coverage: Tasks 1-2 implement the contracts and stable full-course order; Task 3 implements profile validation, skip, blocking, and depth rules; Task 4 enforces path immutability during updates; Task 5 covers the three learner types and documentation.
- Scope control: no task introduces Neo4j calls, LangChain, LangGraph, FastAPI, persistence, resource generation, diagnosis algorithms, or multi-agent behavior.
- Type consistency: `PlannerPolicy`, `PathStatus`, `ReasonCode`, `PathNode`, `PathDecision`, `PlanningError`, `CoursePlanner`, and `DepthUpdater` retain the same names and signatures throughout.
- Determinism: path ordering and `path_id` use only versioned, canonical inputs; wall-clock time is never generated inside the planning core.
- Data safety: all tests use generated snapshots and version-controlled ontology YAML; raw learner exports remain untracked and untouched.
