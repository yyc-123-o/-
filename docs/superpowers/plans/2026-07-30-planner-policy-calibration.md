# Planner Policy Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate and rank deterministic one-coordinate alternatives for every fixed `PlannerPolicy` parameter group, with a synthetic-labelled, tamper-evident report and CLI.

**Architecture:** Refactor path evaluation to expose reusable candidate case scoring while preserving the strict baseline wrapper. Add a focused planner-calibration module that generates legal coordinate candidates, evaluates them against stored synthetic oracles, ranks them deterministically, and atomically writes a validated report.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, pytest, Ruff, mypy

## Global Constraints

- Preserve all required concepts, stable teaching order, and hard prerequisites.
- Change exactly one parameter coordinate group per candidate.
- Evaluate the dataset baseline separately and exclude it from candidates.
- Never promote a candidate into production configuration.
- Label all current calibration artifacts as synthetic.
- Require no model, API key, database, network, or external Agent.
- Preserve existing strict `evaluate_course_paths()` policy-mismatch behavior.
- Use test-first red-green-refactor cycles and commit each independently testable task.

---

### Task 1: Reusable Candidate Path Evaluation

**Files:**
- Modify: `src/skillforge_kb/evaluation/path_evaluation.py`
- Modify: `src/skillforge_kb/evaluation/__init__.py`
- Modify: `tests/unit/evaluation/test_path_evaluation.py`

**Interfaces:**
- Consumes: `OntologyCatalog`, `SyntheticPlanningDataset`, and explicit `PlannerPolicy`.
- Produces: `evaluate_course_path_cases(...) -> tuple[PathEvaluationCaseResult, ...]`.

- [ ] **Step 1: Write failing candidate-evaluation tests**

```python
def test_candidate_case_evaluation_accepts_a_different_policy(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    candidate = PlannerPolicy(
        version="planner-policy.candidate.v1",
        intermediate_threshold=0.70,
    )
    results = evaluate_course_path_cases(catalog, dataset, candidate)
    assert len(results) == 8
    assert any(item.depth_mismatch_ids for item in results)


def test_strict_report_still_rejects_a_different_policy(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    with pytest.raises(ValueError, match="policy"):
        evaluate_course_paths(
            catalog,
            dataset,
            PlannerPolicy(version="planner-policy.candidate.v1"),
        )
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run `uv run pytest tests/unit/evaluation/test_path_evaluation.py -q`. Expected: import failure for `evaluate_course_path_cases`.

- [ ] **Step 3: Extract case evaluation**

Move the existing case loop into `evaluate_course_path_cases()`. It validates the dataset and graph version but deliberately does not compare dataset policy metadata with the explicit candidate. `evaluate_course_paths()` retains the current policy metadata check, calls the extracted function, reconstructs metrics, and builds the strict report.

- [ ] **Step 4: Verify and commit Task 1**

```powershell
uv run pytest tests/unit/evaluation -q
uv run ruff check src/skillforge_kb/evaluation tests/unit/evaluation
uv run mypy src/skillforge_kb/evaluation
git add src/skillforge_kb/evaluation tests/unit/evaluation/test_path_evaluation.py
git commit -m "refactor: expose candidate path evaluation"
```

### Task 2: Legal Coordinate Candidate Generation

**Files:**
- Create: `src/skillforge_kb/evaluation/planner_calibration.py`
- Create: `tests/unit/evaluation/test_planner_calibration.py`
- Modify: `src/skillforge_kb/evaluation/__init__.py`

**Interfaces:**
- Consumes: `PlannerPolicy`, `AbilityWeights`, and `build_policy_digest()`.
- Produces: `PlannerPolicyCoordinate`, `PlannerPolicyCandidate`, `PlannerPolicySearchSpace`, `default_planner_policy_search_space()`, `build_planner_search_space_digest()`, and `generate_planner_policy_candidates()`.

- [ ] **Step 1: Write failing search-space tests**

Require deterministic candidates, all seven coordinate groups, one-coordinate-only changes, valid normalized weights and thresholds, unique tunable tuples, baseline exclusion, strictly increasing numeric axes, and rejection of a space with no alternative.

```python
def test_default_candidates_are_deterministic_legal_and_complete() -> None:
    baseline = PlannerPolicy()
    space = default_planner_policy_search_space(baseline)
    first = generate_planner_policy_candidates(space, baseline)
    second = generate_planner_policy_candidates(space, baseline)
    assert first == second
    assert {item.changed_coordinate for item in first} == set(PlannerPolicyCoordinate)
    assert all(item.policy != baseline for item in first)
    assert len({_tunable_values(item.policy) for item in first}) == len(first)
```

- [ ] **Step 2: Run tests and verify RED**

Expected: import failure because `planner_calibration` is absent.

- [ ] **Step 3: Implement coordinate contracts**

`PlannerPolicyCoordinate` has `minimum_confidence`, `skip_mastery`, `skip_confidence`, `readiness_weights`, `intermediate_threshold`, `advanced_threshold`, and `ability_weights`. `PlannerPolicyCandidate` stores the policy, digest, changed coordinate, and baseline/candidate value tuples. `PlannerPolicySearchSpace` stores six strictly increasing float tuples plus unique, valid `AbilityWeights` options.

- [ ] **Step 4: Implement stable candidate generation**

Iterate coordinates in enum order and values in search-space order. Readiness alternatives update `mastery_weight` and complementary `ability_weight` together. Ability alternatives replace the complete vector. Skip baseline-equivalent tunables, reject invalid threshold order through `PlannerPolicy`, deduplicate tunable tuples, and assign versions `planner-policy.candidate.v1.<four-digit-index>`.

- [ ] **Step 5: Verify and commit Task 2**

```powershell
uv run pytest tests/unit/evaluation/test_planner_calibration.py -q
uv run ruff check src/skillforge_kb/evaluation tests/unit/evaluation
uv run mypy src/skillforge_kb/evaluation
git add src/skillforge_kb/evaluation tests/unit/evaluation/test_planner_calibration.py
git commit -m "feat: generate planner policy candidates"
```

### Task 3: Candidate Evaluation, Ranking, and Report Integrity

**Files:**
- Modify: `src/skillforge_kb/evaluation/planner_calibration.py`
- Modify: `src/skillforge_kb/evaluation/__init__.py`
- Modify: `tests/unit/evaluation/test_planner_calibration.py`

**Interfaces:**
- Consumes: Task 1 case evaluation and Task 2 candidate specs.
- Produces: `PlannerPolicyEvaluation`, `PlannerPolicyCalibrationReport`, `evaluate_planner_policy()`, `search_planner_policies()`, and report/search-space digest helpers.

- [ ] **Step 1: Write failing evaluation and ranking tests**

Require baseline parity with the strict path report, stable repeated searches, invariant preservation, baseline exclusion, exact ranking reconstruction, best-candidate identity, and report JSON round trips.

```python
def test_baseline_evaluation_matches_strict_report(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    strict = evaluate_course_paths(catalog, dataset)
    baseline = evaluate_planner_policy(catalog, dataset, PlannerPolicy())
    assert baseline.metrics == strict.metrics
    assert baseline.changed_coordinate is None


def test_search_is_deterministic_and_preserves_invariants(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    space = default_planner_policy_search_space(PlannerPolicy())
    first = search_planner_policies(catalog, dataset, space)
    second = search_planner_policies(catalog, dataset, space)
    assert first == second
    assert first.best_fitting_candidate == first.ranked_candidates[0]
    assert all(not item.invariant_failure_case_ids for item in first.ranked_candidates)
```

Also mutate stored ranking, metrics, policy identity, and report digest and require validation failures.

- [ ] **Step 2: Run tests and verify RED**

Expected: missing evaluation/report symbols.

- [ ] **Step 3: Implement evaluation summaries**

`evaluate_planner_policy()` calls `evaluate_course_path_cases()`, reconstructs standard metrics, and records ordered case IDs for skip mismatch, depth mismatch, and any coverage/order/prerequisite invariant failure. The baseline evaluation has null coordinate and empty changed-value tuples; candidate evaluation copies its coordinate metadata.

- [ ] **Step 4: Implement ranking and report validation**

Use this key:

```python
(
    len(evaluation.invariant_failure_case_ids),
    -evaluation.metrics.skip_accuracy,
    -evaluation.metrics.delivery_depth_accuracy,
    -evaluation.metrics.low_confidence_conservative_rate,
    _policy_distance(evaluation.policy, baseline),
    evaluation.policy_digest,
)
```

Validate dataset/search-space digests, common case counts, unique candidate tunables and digests, baseline exclusion, complete sorted order, first-candidate identity, and report digest.

- [ ] **Step 5: Verify and commit Task 3**

```powershell
uv run pytest tests/unit/evaluation/test_planner_calibration.py tests/unit/evaluation/test_path_evaluation.py -q
uv run ruff check src/skillforge_kb/evaluation tests/unit/evaluation
uv run mypy src
git add src/skillforge_kb/evaluation tests/unit/evaluation/test_planner_calibration.py
git commit -m "feat: rank planner policy calibration"
```

### Task 4: CLI, Documentation, Smoke Run, and Final Gates

**Files:**
- Modify: `src/skillforge_kb/evaluation/planner_calibration.py`
- Modify: `src/skillforge_kb/evaluation/__init__.py`
- Modify: `src/skillforge_kb/cli.py`
- Modify: `tests/unit/evaluation/test_serialization.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `write_planner_policy_calibration_report()` and `planning-calibrate-policy`.

- [ ] **Step 1: Write failing serialization and CLI tests**

Require atomic report replacement, valid round trip, no temporary file, successful default CLI search, input-overwrite rejection, and concise invalid-dataset output.

- [ ] **Step 2: Implement atomic report writing and CLI**

The command loads the synthetic dataset, validates the catalog and baseline policy, creates the default search space, runs calibration, writes JSON through a sibling temporary file, and echoes case/candidate counts. Catch only expected `OSError`, `ValueError`, and `ValidationError`.

- [ ] **Step 3: Document and run the default experiment**

```powershell
uv run skillforge-kb planning-generate-synthetic --output-file reports/generated/synthetic-planning-dataset.json
uv run skillforge-kb planning-calibrate-policy --dataset-file reports/generated/synthetic-planning-dataset.json --output-file reports/generated/planner-policy-calibration.json
```

Inspect candidate count, best-candidate coordinate, baseline/candidate fit, and invariant failures. State explicitly that synthetic fit is not real teaching performance.

- [ ] **Step 4: Commit Task 4**

```powershell
git add src/skillforge_kb/evaluation src/skillforge_kb/cli.py tests/unit/evaluation tests/unit/test_cli.py README.md
git commit -m "feat: expose planner policy calibration"
```

- [ ] **Step 5: Run fresh final gates**

```powershell
uv run pytest tests/unit -q
uv run pytest --collect-only -q
uv run ruff check .
uv run mypy src
uv lock --check --offline
git diff --check
```

Expected: all commands exit `0`; five collected external-service integration tests remain outside the unit-test run.
