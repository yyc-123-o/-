# Course Path Offline Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate 60 reproducible synthetic learner profiles and evaluate the existing deterministic course planner with auditable path, skip, depth, coverage, and prerequisite metrics.

**Architecture:** Add a standalone `evaluation` package. Frozen Pydantic contracts own artifact validation, a stratified seeded generator owns synthetic cases and their independent expected decisions, and a path evaluator owns planner execution plus aggregate reconstruction. Typer commands provide atomic JSON generation and evaluation without external services.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, pytest, Ruff, mypy

## Global Constraints

- Preserve the complete required-concept set and stable teaching order.
- Never bypass, remove, or reorder hard prerequisites.
- Label every dataset and report as `synthetic`.
- Default to exactly 60 cases, seed `20260730`, and all eight scenario cohorts.
- Use only a local `random.Random`; never modify global random state.
- Derive artifact IDs from canonical JSON and fixed metadata, never wall-clock time.
- Reject graph-version, policy-version, policy-digest, and artifact-digest mismatches.
- Do not implement BKT, IRT, forgetting, adaptive item selection, or learning-gain metrics.
- Do not require an API key, model, network, Agent, Neo4j, or PostgreSQL.
- Preserve the four existing untracked user paths and do not stage them.

---

### Task 1: Synthetic Evaluation Contracts and Generator

**Files:**
- Create: `src/skillforge_kb/evaluation/__init__.py`
- Create: `src/skillforge_kb/evaluation/models.py`
- Create: `src/skillforge_kb/evaluation/synthetic.py`
- Create: `tests/unit/evaluation/__init__.py`
- Create: `tests/unit/evaluation/conftest.py`
- Create: `tests/unit/evaluation/test_synthetic.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, `LearnerProfileSnapshot`, `PlannerPolicy`, `DepthLevel`, and `build_policy_digest()`.
- Produces: `ScenarioCohort`, `ExpectedNodeDecision`, `SyntheticPlanningCase`, `SyntheticPlanningDataset`, `build_synthetic_dataset_digest()`, and `generate_synthetic_dataset()`.

- [ ] **Step 1: Write failing model and generator tests**

Create tests with this public shape:

```python
def test_default_generation_is_deterministic_and_stratified(catalog) -> None:
    first = generate_synthetic_dataset(catalog)
    second = generate_synthetic_dataset(catalog)

    assert first == second
    assert len(first.cases) == 60
    assert {case.cohort for case in first.cases} == set(ScenarioCohort)
    counts = Counter(case.cohort for case in first.cases)
    assert max(counts.values()) - min(counts.values()) <= 1
    assert first.data_kind == "synthetic"


def test_generation_changes_values_but_not_allocation_when_seed_changes(catalog) -> None:
    first = generate_synthetic_dataset(catalog, seed=1)
    second = generate_synthetic_dataset(catalog, seed=2)

    assert tuple(case.cohort for case in first.cases) == tuple(
        case.cohort for case in second.cases
    )
    assert first.dataset_digest != second.dataset_digest


def test_generation_rejects_too_few_cases(catalog) -> None:
    with pytest.raises(ValueError, match="at least eight"):
        generate_synthetic_dataset(catalog, case_count=7)
```

Also require unique case IDs, one expected decision per required concept, profile/graph consistency, expected skip/depth consistency, and digest mutation detection through `model_validate()`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/evaluation/test_synthetic.py -q
```

Expected: collection fails because `skillforge_kb.evaluation` does not exist.

- [ ] **Step 3: Implement immutable contracts**

Define these exact public fields in `models.py`:

```python
class ScenarioCohort(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    UNEVEN = "uneven"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_EVIDENCE = "missing_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    BOUNDARY = "boundary"


class ExpectedNodeDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    should_skip: bool
    delivery_depth: DepthLevel | None


class SyntheticPlanningCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    cohort: ScenarioCohort
    tags: tuple[str, ...] = Field(min_length=1)
    profile: LearnerProfileSnapshot
    expected_nodes: tuple[ExpectedNodeDecision, ...] = Field(min_length=1)


class SyntheticPlanningDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["synthetic-planning-dataset.v1"] = (
        "synthetic-planning-dataset.v1"
    )
    data_kind: Literal["synthetic"] = "synthetic"
    data_version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    seed: int
    generated_at: datetime
    cases: tuple[SyntheticPlanningCase, ...] = Field(min_length=8)
    dataset_digest: str = Field(pattern=r"^synthetic_dataset_[0-9a-f]{64}$")
```

Validators enforce unique case IDs, a common graph version, unique expected concept IDs, `should_skip` requiring null depth, non-skipped decisions requiring depth, and a recomputed digest over all fields except `dataset_digest`.

- [ ] **Step 4: Implement the stratified generator**

Use:

```python
DEFAULT_SYNTHETIC_CASE_COUNT = 60
DEFAULT_SYNTHETIC_SEED = 20260730
DEFAULT_GENERATED_AT = datetime(2026, 7, 30, tzinfo=UTC)
```

Allocate case ordinals round-robin over `tuple(ScenarioCohort)`. Create a fresh `Random(seed)` and bounded cohort-specific mastery, confidence, and ability values. Build valid `KnowledgeMastery` and `AbilityScore` records only; missing-evidence variants omit records rather than using invalid values.

Implement `_expected_nodes(catalog, profile, policy)` independently from `CoursePlanner`: apply skip thresholds, hard-prerequisite evidence, confidence floors, readiness weights, and depth thresholds directly to profile facts. Return decisions in `stable_required_concept_ids(catalog)` order. Do not import or invoke `CoursePlanner` from `synthetic.py`.

- [ ] **Step 5: Export and verify Task 1**

Export the Task 1 public symbols from `evaluation/__init__.py`, then run:

```powershell
uv run pytest tests/unit/evaluation/test_synthetic.py -q
uv run ruff check src/skillforge_kb/evaluation tests/unit/evaluation
uv run mypy src/skillforge_kb/evaluation
```

Expected: all commands exit `0`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/skillforge_kb/evaluation tests/unit/evaluation
git commit -m "feat: generate synthetic planning profiles"
```

### Task 2: Course Path Evaluator and Validated Report

**Files:**
- Create: `src/skillforge_kb/evaluation/path_evaluation.py`
- Create: `tests/unit/evaluation/test_path_evaluation.py`
- Modify: `src/skillforge_kb/evaluation/models.py`
- Modify: `src/skillforge_kb/evaluation/__init__.py`

**Interfaces:**
- Consumes: `SyntheticPlanningDataset`, `OntologyCatalog`, `CoursePlanner`, and `PlannerPolicy`.
- Produces: `PathEvaluationCaseResult`, `PathEvaluationMetrics`, `PathEvaluationReport`, `build_path_evaluation_report_digest()`, and `evaluate_course_paths()`.

- [ ] **Step 1: Write failing evaluator tests**

Add tests equivalent to:

```python
def test_default_planner_preserves_graph_invariants(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog)
    report = evaluate_course_paths(catalog, dataset)

    assert report.metrics.hard_prerequisite_violation_rate == 0.0
    assert report.metrics.required_concept_coverage_rate == 1.0
    assert report.metrics.path_order_stability_rate == 1.0
    assert report.metrics.skip_accuracy == 1.0
    assert report.metrics.delivery_depth_accuracy == 1.0
    assert len(report.case_results) == 60


def test_low_confidence_cases_are_conservative(catalog) -> None:
    report = evaluate_course_paths(catalog, generate_synthetic_dataset(catalog))
    assert report.metrics.low_confidence_case_count > 0
    assert report.metrics.low_confidence_conservative_rate == 1.0


def test_evaluator_rejects_policy_mismatch(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog)
    changed = PlannerPolicy(version="planner-policy.changed")
    with pytest.raises(ValueError, match="policy"):
        evaluate_course_paths(catalog, dataset, changed)
```

Also require a stable report digest, aggregate reconstruction after JSON round trip, and validation failure after mutating a stored metric or case result.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/evaluation/test_path_evaluation.py -q
```

Expected: imports fail because the evaluator symbols do not exist.

- [ ] **Step 3: Implement result contracts**

Use frozen, `extra="forbid"` Pydantic models. `PathEvaluationCaseResult` stores case/cohort/tags, `path_id`, returned and expected counts, prerequisite edge and violation counts, ordered mismatch-ID tuples, `order_stable`, and optional low-confidence conservatism. `PathEvaluationMetrics` stores every integer numerator and denominator alongside these derived values:

```python
hard_prerequisite_violation_rate: float = Field(ge=0, le=1)
required_concept_coverage_rate: float = Field(ge=0, le=1)
skip_accuracy: float = Field(ge=0, le=1)
delivery_depth_accuracy: float = Field(ge=0, le=1)
path_order_stability_rate: float = Field(ge=0, le=1)
low_confidence_conservative_rate: float = Field(ge=0, le=1)
mean_learning_node_count: float = Field(ge=0)
mean_skipped_node_count: float = Field(ge=0)
```

`PathEvaluationReport` carries the dataset provenance, planner policy provenance, ordered case results, metrics, the literal synthetic disclaimer, and `report_digest`. Validators recompute all rates, means, case counts, and both artifact digests.

- [ ] **Step 4: Implement deterministic evaluation**

For each ordered synthetic case:

1. run `CoursePlanner(catalog, policy).plan(case.profile)`;
2. compare returned concept IDs with required IDs;
3. count hard-prerequisite edges whose source index is not lower than target index;
4. compare actual skip flags with the stored oracle;
5. compare delivery depth for every oracle non-skip decision;
6. require exact stable required-concept order;
7. for `LOW_CONFIDENCE`, require no skipped nodes and intro depth for every learning node.

Aggregate only from integer counts. Use `0.0` only for a rate with a zero denominator that the model explicitly allows; the default dataset must have non-zero denominators for every metric.

- [ ] **Step 5: Export and verify Task 2**

Run:

```powershell
uv run pytest tests/unit/evaluation -q
uv run ruff check src/skillforge_kb/evaluation tests/unit/evaluation
uv run mypy src/skillforge_kb/evaluation
```

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/skillforge_kb/evaluation tests/unit/evaluation
git commit -m "feat: evaluate synthetic course paths"
```

### Task 3: Atomic JSON Artifacts and CLI Commands

**Files:**
- Modify: `src/skillforge_kb/evaluation/synthetic.py`
- Modify: `src/skillforge_kb/evaluation/path_evaluation.py`
- Modify: `src/skillforge_kb/evaluation/__init__.py`
- Modify: `src/skillforge_kb/cli.py`
- Create: `tests/unit/evaluation/test_serialization.py`
- Modify: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: Task 1 generation and Task 2 evaluation APIs.
- Produces: `load_synthetic_dataset()`, `write_synthetic_dataset()`, `write_path_evaluation_report()`, `planning-generate-synthetic`, and `planning-evaluate`.

- [ ] **Step 1: Write failing serialization tests**

Require canonical UTF-8 JSON plus newline, a successful Pydantic round trip, replacement of an existing output, no leftover temporary file, and rejection of a tampered dataset digest.

```python
def test_dataset_write_and_load_round_trip(tmp_path, catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    output = tmp_path / "dataset.json"
    write_synthetic_dataset(dataset, output)

    assert output.read_bytes().endswith(b"\n")
    assert load_synthetic_dataset(output) == dataset
    assert not (tmp_path / ".dataset.json.tmp").exists()
```

- [ ] **Step 2: Run serialization tests and verify RED**

Expected: imports fail because read/write helpers do not exist.

- [ ] **Step 3: Implement atomic artifact helpers**

Serialize with `model_dump(mode="json")`, `ensure_ascii=False`, `indent=2`, and `sort_keys=True`. Write to `.<name>.tmp`, then call `replace(output_path)`. Load through `SyntheticPlanningDataset.model_validate_json()` so digest and structural validators run on every read.

- [ ] **Step 4: Write failing CLI tests**

Use `typer.testing.CliRunner` to require successful generation/evaluation, default 60-case output, concise invalid-dataset errors, and rejection when an output overwrites the course, relation, or dataset input.

```python
def test_planning_commands_generate_and_evaluate(tmp_path) -> None:
    dataset_path = tmp_path / "synthetic.json"
    report_path = tmp_path / "report.json"
    generated = runner.invoke(app, [
        "planning-generate-synthetic", "--output-file", str(dataset_path)
    ])
    evaluated = runner.invoke(app, [
        "planning-evaluate", "--dataset-file", str(dataset_path),
        "--output-file", str(report_path),
    ])
    assert generated.exit_code == 0
    assert evaluated.exit_code == 0
    assert SyntheticPlanningDataset.model_validate_json(
        dataset_path.read_text(encoding="utf-8")
    ).cases
    assert PathEvaluationReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    ).metrics.hard_prerequisite_violation_rate == 0.0
```

- [ ] **Step 5: Run CLI tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/evaluation/test_serialization.py tests/unit/test_cli.py -q
```

Expected: CLI tests fail because both commands are absent.

- [ ] **Step 6: Implement both commands**

Add `planning_generate_synthetic()` and `planning_evaluate()` to `cli.py`. Reuse `_load_validated_catalog()` and `_output_path_outside_inputs()`. Convert `OSError`, `ValueError`, and `ValidationError` into `typer.BadParameter`; never catch unexpected programming errors. Echo the resolved output path and the synthetic case count.

- [ ] **Step 7: Verify and commit Task 3**

```powershell
uv run pytest tests/unit/evaluation tests/unit/test_cli.py -q
uv run ruff check src/skillforge_kb/evaluation src/skillforge_kb/cli.py tests/unit/evaluation tests/unit/test_cli.py
uv run mypy src
git add src/skillforge_kb/evaluation src/skillforge_kb/cli.py tests/unit/evaluation tests/unit/test_cli.py
git commit -m "feat: expose planning evaluation commands"
```

### Task 4: Documentation, Generated Smoke Artifacts, and Final Gates

**Files:**
- Modify: `README.md`
- Generate for local verification only: `reports/generated/synthetic-planning-dataset.json`
- Generate for local verification only: `reports/generated/course-path-evaluation.json`

**Interfaces:**
- Consumes: the two CLI commands.
- Produces: documented commands and fresh verification evidence; generated smoke artifacts remain untracked unless an existing repository rule says otherwise.

- [ ] **Step 1: Document the workflow**

Add a README section with both exact PowerShell commands, explain the eight cohorts and metrics, and state that the outputs are synthetic regression evidence rather than measured educational impact.

- [ ] **Step 2: Run both commands with defaults**

```powershell
uv run skillforge-kb planning-generate-synthetic --output-file reports/generated/synthetic-planning-dataset.json
uv run skillforge-kb planning-evaluate --dataset-file reports/generated/synthetic-planning-dataset.json --output-file reports/generated/course-path-evaluation.json
```

Expected: 60 cases; zero prerequisite violations; full required-concept coverage; stable order.

- [ ] **Step 3: Commit documentation only**

```powershell
git add README.md
git commit -m "docs: explain course path evaluation"
```

- [ ] **Step 4: Run complete verification gates**

```powershell
uv run pytest tests/unit -q
uv run pytest --collect-only -q
uv run ruff check .
uv run mypy src
uv lock --check --offline
git diff --check 34fcf69..HEAD
```

Expected: all commands exit `0`; collection includes five external-service integration tests not executed by the unit-test command.

- [ ] **Step 5: Audit scope and worktree state**

Confirm the evaluator never imports BKT/IRT/model APIs, generated artifacts state `synthetic`, metrics reconstruct from integer counts, and no pre-existing untracked user path is staged. Run:

```powershell
git status --short
git log --oneline -8
```
