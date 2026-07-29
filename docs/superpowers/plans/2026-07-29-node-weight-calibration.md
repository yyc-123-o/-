# Node Weight Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, auditable node-weight calibration package that evaluates labelled feature snapshots, searches legal policy grids, and reports ablation and sensitivity results without modifying course paths or production policy files.

**Architecture:** Extract the support formula into a pure scoring function shared by `NodeWeightEngine` and calibration. Keep calibration in `planning/calibration.py`, where frozen Pydantic contracts validate data provenance, generate legal candidates, evaluate the baseline and alternatives, and produce machine-readable reports.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Ruff, mypy

## Global Constraints

- Do not implement BKT, IRT, adaptive item selection, or any paper-dependent model.
- Do not accept or return `PathDecision` from calibration APIs.
- Do not add, remove, reorder, skip, or complete course nodes.
- Do not automatically replace or publish the production `NodeWeightPolicy`.
- Mark every dataset as `synthetic`, `expert_labelled`, or `observed`.
- Use the production scoring function for all calibration evaluations; do not duplicate the formula.
- Preserve existing `NodeAdaptationDecision` values and digests for identical inputs.
- Require no API key, model, database, network service, or external Agent.

---

### Task 1: Extract the Shared Node Support Scorer

**Files:**
- Modify: `src/skillforge_kb/planning/adaptation.py`
- Modify: `tests/unit/planning/test_adaptation.py`

**Interfaces:**
- Consumes: `NodeWeightPolicy`, `FactorContribution`, `SupportIntensity`.
- Produces: `NodeWeightFeatures`, `NodeSupportScore`, `score_node_support()`, `build_node_weight_policy_digest()`.

- [ ] **Step 1: Write failing scoring-contract tests**

Add imports for the four new public symbols, then add tests equivalent to:

```python
def test_pure_support_score_applies_weighted_factors_and_floor() -> None:
    policy = NodeWeightPolicy()
    score = score_node_support(
        NodeWeightFeatures(
            mastery_gap=0.5,
            error_risk=0.2,
            ability_gap=0.3,
            support_floor=0.6,
        ),
        policy,
    )
    assert score.support_need_score == pytest.approx(0.6)
    assert score.support_intensity is SupportIntensity.SCAFFOLDED
    assert sum(item.contribution for item in score.contributions) == pytest.approx(0.6)


def test_pure_support_score_forces_blocked_remediation() -> None:
    score = score_node_support(
        NodeWeightFeatures(
            mastery_gap=0.0,
            error_risk=0.0,
            ability_gap=0.0,
            support_floor=0.0,
            blocked=True,
        ),
        NodeWeightPolicy(),
    )
    assert score.support_intensity is SupportIntensity.REMEDIATION


def test_node_weight_policy_digest_is_stable_and_content_sensitive() -> None:
    baseline = NodeWeightPolicy()
    same = NodeWeightPolicy.model_validate(baseline.model_dump())
    changed = baseline.model_copy(update={"compact_threshold": 0.2})
    assert build_node_weight_policy_digest(baseline) == build_node_weight_policy_digest(same)
    assert build_node_weight_policy_digest(baseline) != build_node_weight_policy_digest(changed)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/planning/test_adaptation.py -q
```

Expected: collection fails because the new symbols are not defined.

- [ ] **Step 3: Implement frozen feature and score contracts**

Add these contracts after `FactorContribution`:

```python
class NodeWeightFeatures(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mastery_gap: float = Field(ge=0, le=1)
    error_risk: float = Field(ge=0, le=1)
    ability_gap: float = Field(ge=0, le=1)
    support_floor: float = Field(default=0.0, ge=0, le=1)
    blocked: bool = False


class NodeSupportScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    support_need_score: float = Field(ge=0, le=1)
    support_intensity: SupportIntensity
    contributions: tuple[FactorContribution, ...]

    @model_validator(mode="after")
    def validate_contributions(self) -> "NodeSupportScore":
        if not isclose(
            sum(item.contribution for item in self.contributions),
            self.support_need_score,
            abs_tol=1e-9,
        ):
            raise ValueError("support contributions must sum to support need score")
        return self
```

- [ ] **Step 4: Implement the shared scorer and public digest**

Implement `score_node_support(features, policy)` using the existing three contributions, append a `conservative_evidence_floor` contribution when needed, and select intensity in this order: blocked remediation, scaffolded threshold, compact threshold, compact. Add:

```python
def build_node_weight_policy_digest(policy: NodeWeightPolicy) -> str:
    return f"node_policy_{_hash(policy.model_dump(mode='json'))}"
```

- [ ] **Step 5: Delegate production evaluation to the scorer**

In `NodeWeightEngine.__init__()`, build the digest through `build_node_weight_policy_digest()`. In `evaluate()`, derive `NodeWeightFeatures` from the existing profile facts, invoke `score_node_support()`, and use its score, intensity, and contributions when constructing `NodeAdaptationPayload`. Keep readiness, delivery depth, reasons, assessment emphasis, and output digest behaviour unchanged.

- [ ] **Step 6: Run focused and regression tests**

Run:

```powershell
uv run pytest tests/unit/planning/test_adaptation.py tests/unit/resources/test_briefs.py tests/unit/agents/test_planning_agent.py -q
uv run ruff check src/skillforge_kb/planning/adaptation.py tests/unit/planning/test_adaptation.py
uv run mypy src/skillforge_kb/planning/adaptation.py
```

Expected: all commands exit `0` and existing decisions remain unchanged.

- [ ] **Step 7: Commit Task 1**

```powershell
git add src/skillforge_kb/planning/adaptation.py tests/unit/planning/test_adaptation.py
git commit -m "refactor: extract node support scorer"
```

### Task 2: Calibration Dataset, Candidate Grid, Evaluation, and Search

**Files:**
- Create: `src/skillforge_kb/planning/calibration.py`
- Create: `tests/unit/planning/test_calibration.py`

**Interfaces:**
- Consumes: `NodeWeightFeatures`, `NodeWeightPolicy`, `SupportIntensity`, `score_node_support()`, `build_node_weight_policy_digest()`.
- Produces: calibration models plus `build_calibration_dataset_digest()`, `generate_node_weight_policies()`, `evaluate_node_weight_policy()`, and `search_node_weight_policies()`.

- [ ] **Step 1: Write failing dataset and grid tests**

Create a dataset fixture with compact, standard, scaffolded, and blocked examples. Add tests that require:

```python
def test_dataset_requires_unique_cases_and_consistent_blocked_labels(dataset) -> None:
    duplicate = dataset.model_copy(update={"examples": (dataset.examples[0],) * 2})
    with pytest.raises(ValidationError, match="case IDs"):
        NodeWeightCalibrationDataset.model_validate(duplicate.model_dump())

    with pytest.raises(ValidationError, match="blocked examples"):
        NodeWeightCalibrationExample(
            case_id="invalid-blocked",
            features=NodeWeightFeatures(
                mastery_gap=0.0,
                error_risk=0.0,
                ability_gap=0.0,
                blocked=True,
            ),
            expected_support_intensity=SupportIntensity.STANDARD,
        )


def test_candidate_generation_is_deterministic_and_legal(search_space) -> None:
    first = generate_node_weight_policies(search_space)
    second = generate_node_weight_policies(search_space)
    assert first == second
    assert first
    assert all(
        item.mastery_gap_weight + item.error_risk_weight + item.ability_gap_weight
        == pytest.approx(1.0)
        for item in first
    )
    assert all(item.compact_threshold < item.scaffolded_threshold for item in first)
```

Also reject unordered/duplicate search axes and a grid with no valid weight sum.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/planning/test_calibration.py -q
```

Expected: collection fails because `planning.calibration` does not exist.

- [ ] **Step 3: Implement input models and digests**

Create:

```python
class CalibrationDataKind(StrEnum):
    SYNTHETIC = "synthetic"
    EXPERT_LABELLED = "expert_labelled"
    OBSERVED = "observed"


class NodeWeightFactor(StrEnum):
    MASTERY_GAP = "mastery_gap_weight"
    ERROR_RISK = "error_risk_weight"
    ABILITY_GAP = "ability_gap_weight"


class NodeWeightCalibrationExample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    case_id: str = Field(min_length=1)
    features: NodeWeightFeatures
    expected_support_intensity: SupportIntensity
    target_support_need_score: float | None = Field(default=None, ge=0, le=1)


class NodeWeightCalibrationDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["node-weight-calibration-dataset.v1"] = (
        "node-weight-calibration-dataset.v1"
    )
    dataset_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    data_kind: CalibrationDataKind
    examples: tuple[NodeWeightCalibrationExample, ...] = Field(min_length=1)
```

Add validators for blocked labels and unique case IDs. Build the dataset digest with canonical ASCII JSON, sorted keys, and compact separators.

- [ ] **Step 4: Implement and validate the search space**

Use bounded `Annotated[float, Field(ge=0, le=1)]` axis items. Require every axis to be non-empty and strictly increasing. Generate the Cartesian product in field order, reject any positive factor-sum overshoot, allow at most `1e-9` undershoot, retain legal policies, and assign stable versions `<policy_version_prefix>.<four-digit-index>`. Raise `ValueError("search space contains no valid policy")` when filtering removes every combination.

- [ ] **Step 5: Write failing evaluation and search tests**

Add tests that require exact per-case predictions, correct match rate and mean absolute error, stable report JSON round-trips, baseline exclusion, repeated-search equality, and ranking by label fit followed by distance from the baseline.

```python
def test_policy_evaluation_reports_label_fit_and_score_error(dataset) -> None:
    evaluation = evaluate_node_weight_policy(dataset, NodeWeightPolicy())
    assert evaluation.case_count == 4
    assert evaluation.exact_match_rate == 1.0
    assert evaluation.target_case_count == 4
    assert evaluation.mean_absolute_error == pytest.approx(0.0)


def test_search_is_deterministic_and_does_not_return_the_baseline(dataset, search_space) -> None:
    baseline = NodeWeightPolicy()
    first = search_node_weight_policies(dataset, search_space, baseline)
    second = search_node_weight_policies(dataset, search_space, baseline)
    assert first == second
    assert first.baseline.policy == baseline
    assert all(
        _tunable_values(item.policy) != _tunable_values(baseline)
        for item in first.ranked_candidates
    )
    assert first.best_fitting_candidate == first.ranked_candidates[0]
    assert NodeWeightCalibrationReport.model_validate_json(first.model_dump_json()) == first
```

- [ ] **Step 6: Run evaluation tests and verify RED**

Run only the new evaluation/search tests. Expected: failures because result models and functions are missing.

- [ ] **Step 7: Implement evaluation result models**

Add frozen models:

```python
class NodeWeightCaseResult(BaseModel):
    case_id: str
    predicted_support_need_score: float = Field(ge=0, le=1)
    predicted_support_intensity: SupportIntensity
    intensity_matches: bool
    absolute_error: float | None = Field(default=None, ge=0, le=1)


class NodeWeightPolicyEvaluation(BaseModel):
    policy: NodeWeightPolicy
    policy_digest: str
    case_count: int = Field(ge=1)
    exact_match_count: int = Field(ge=0)
    exact_match_rate: float = Field(ge=0, le=1)
    target_case_count: int = Field(ge=0)
    mean_absolute_error: float | None = Field(default=None, ge=0, le=1)
    case_results: tuple[NodeWeightCaseResult, ...]


class NodeWeightCalibrationReport(BaseModel):
    schema_version: Literal["node-weight-calibration-report.v1"] = (
        "node-weight-calibration-report.v1"
    )
    dataset_id: str
    data_version: str
    data_kind: CalibrationDataKind
    dataset_digest: str
    baseline: NodeWeightPolicyEvaluation
    ranked_candidates: tuple[NodeWeightPolicyEvaluation, ...] = Field(min_length=1)
    best_fitting_candidate: NodeWeightPolicyEvaluation
```

All models use `ConfigDict(frozen=True, extra="forbid")`; add consistency validators for counts,
rates, result lengths, unique case IDs, policy digests, common ordered case/target coverage,
baseline exclusion, unique candidate tunables, complete ranking order, and the best candidate.

- [ ] **Step 8: Implement evaluation and deterministic search**

`evaluate_node_weight_policy()` calls `score_node_support()` once per ordered example. Search evaluates the baseline separately, excludes candidates with identical five tunable values, and raises `ValueError("search space contains no alternative policy")` when none remain.

Sort alternatives by first assigning `error = evaluation.mean_absolute_error`, then using:

```python
(
    -evaluation.exact_match_rate,
    0.0 if error is None else error,
    _policy_distance(evaluation.policy, baseline),
    evaluation.policy_digest,
)
```

Use explicit `is None` handling rather than truthiness for mean absolute error.

- [ ] **Step 9: Verify Task 2**

Run:

```powershell
uv run pytest tests/unit/planning/test_calibration.py -q
uv run ruff check src/skillforge_kb/planning/calibration.py tests/unit/planning/test_calibration.py
uv run mypy src/skillforge_kb/planning/calibration.py
```

- [ ] **Step 10: Commit Task 2**

```powershell
git add src/skillforge_kb/planning/calibration.py tests/unit/planning/test_calibration.py
git commit -m "feat: search node weight calibration candidates"
```

### Task 3: Ablation, Sensitivity, and Public API

**Files:**
- Modify: `src/skillforge_kb/planning/calibration.py`
- Modify: `src/skillforge_kb/planning/__init__.py`
- Modify: `tests/unit/planning/test_calibration.py`

**Interfaces:**
- Consumes: Task 2 datasets, reports, and policy evaluation.
- Produces: `NodeWeightAblationResult`, `NodeWeightSensitivityPoint`, `evaluate_node_weight_ablations()`, `summarize_node_weight_sensitivity()`, and public planning exports.

- [ ] **Step 1: Write failing ablation tests**

```python
def test_default_policy_ablation_removes_each_factor_and_renormalizes(dataset) -> None:
    results = evaluate_node_weight_ablations(dataset, NodeWeightPolicy())
    assert tuple(item.removed_factor for item in results) == tuple(NodeWeightFactor)
    for item in results:
        assert getattr(item.evaluation.policy, item.removed_factor.value) == 0.0
        assert sum(_weight_values(item.evaluation.policy)) == pytest.approx(1.0)
        assert item.evaluation.case_count == len(dataset.examples)


def test_ablation_rejects_a_policy_with_no_remaining_weight(dataset) -> None:
    policy = NodeWeightPolicy(
        mastery_gap_weight=1.0,
        error_risk_weight=0.0,
        ability_gap_weight=0.0,
    )
    with pytest.raises(ValueError, match="no positive remaining weight"):
        evaluate_node_weight_ablations(dataset, policy)
```

- [ ] **Step 2: Run ablation tests and verify RED**

Expected: imports fail because ablation result/function are missing.

- [ ] **Step 3: Implement proportional ablation**

For each positive factor, set it to zero and divide each remaining factor by their sum. Use version `<baseline.version>.ablate-<factor-name>`. Preserve both thresholds. Return results in `NodeWeightFactor` enum order. If a positive factor is the only positive weight, raise the specified error rather than emitting an invalid policy.

- [ ] **Step 4: Write failing sensitivity tests**

Require one point per distinct `(factor, value)` present in ranked candidates. Verify stable ordering by factor enum then numeric value, correct candidate counts, arithmetic mean match rate, optional arithmetic mean score error, and repeated-call equality.

- [ ] **Step 5: Run sensitivity tests and verify RED**

Expected: imports fail because sensitivity model/function are missing.

- [ ] **Step 6: Implement descriptive sensitivity summaries**

Create:

```python
class NodeWeightSensitivityPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    factor: NodeWeightFactor
    value: float = Field(ge=0, le=1)
    candidate_count: int = Field(ge=1)
    mean_exact_match_rate: float = Field(ge=0, le=1)
    mean_absolute_error: float | None = Field(default=None, ge=0, le=1)
```

Group `report.ranked_candidates` by each factor value and use `statistics.fmean`. Dataset target coverage is common to every candidate, so error values are either present for all evaluations or absent for all.

- [ ] **Step 7: Export the supported API**

Update `planning/__init__.py` to export the production scoring types/functions and all calibration models/functions. Keep existing exports intact.

- [ ] **Step 8: Verify Task 3**

Run:

```powershell
uv run pytest tests/unit/planning/test_calibration.py tests/unit/planning/test_adaptation.py -q
uv run ruff check src/skillforge_kb/planning tests/unit/planning
uv run mypy src
```

- [ ] **Step 9: Commit Task 3**

```powershell
git add src/skillforge_kb/planning/calibration.py src/skillforge_kb/planning/__init__.py tests/unit/planning/test_calibration.py
git commit -m "feat: report node weight ablation and sensitivity"
```

### Task 4: Final Verification

**Files:**
- Verify all files changed in Tasks 1-3.

- [ ] **Step 1: Run complete gates**

```powershell
uv run pytest tests/unit -q
uv run pytest --collect-only -q
uv run ruff check .
uv run mypy src
uv lock --check --offline
git diff --check dcdb6e2..HEAD
```

- [ ] **Step 2: Review requirements and scope**

Confirm that production and calibration share one scorer, all reports preserve data provenance and digests, ranking never mutates production policy, calibration never imports `PathDecision`, and no BKT/IRT/adaptive-testing/model dependency entered the diff.

- [ ] **Step 3: Review branch state**

Run `git status --short` and `git log --oneline -8`. The tracked worktree must be clean and every implementation commit must be based on `dcdb6e2` plus the design/plan commits.
