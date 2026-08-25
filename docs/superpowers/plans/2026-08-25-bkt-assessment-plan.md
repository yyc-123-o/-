# 平台侧 BKT 知识追踪实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有规则策略默认行为的前提下，为平台增加可独立调用、可审计、可测试的标准 BKT 知识追踪更新器。

**Architecture:** 新增 `assessment/bkt.py`，定义 BKT 参数、状态和结果模型，并复用 `AssessmentEvent`、`AssessmentLedger`、`OntologyCatalog` 的校验语义。BKT 通过 `apply_bkt_event` 显式调用；现有 `apply_assessment_event` 保持规则模型，两个结果可并列比较。

**Tech Stack:** Python 3.12、Pydantic v2、pytest、现有 `skillforge_kb` 领域模型。

## Global Constraints

- 不修改 `AssessmentLedger`、`LearnerProfileSnapshot` 的 JSON 协议。
- 不改变 `apply_assessment_event` 的默认规则行为。
- 所有新增生产代码必须先有一个已验证失败的测试。
- 概率和掌握度始终限制在 `[0, 1]`；禁止产生 NaN 或无穷值。
- 不实现遗忘、IRT 融合、在线参数估计或前端切换器。

---

### Task 1: BKT 参数与纯概率更新

**Files:**
- Create: `tests/unit/assessment/test_bkt.py`
- Create: `src/skillforge_kb/assessment/bkt.py`

**Interfaces:**
- Produces `BktParameters` 和 `update_bkt_probability(prior_mastery, correct, parameters)`。
- `BktParameters` 字段：`p_l0=0.2`、`p_transition=0.1`、`p_guess=0.2`、`p_slip=0.1`、`model_version="bkt.v1"`、`parameter_version="bkt-default.v1"`。
- `update_bkt_probability` 先按答题结果做后验，再应用学习转移，返回 float。

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from datetime import UTC, datetime
from skillforge_kb.assessment import AssessmentEvent
from pydantic import ValidationError
from skillforge_kb.assessment.bkt import BktParameters, update_bkt_probability

def event_factory(**overrides: object) -> AssessmentEvent:
    payload: dict[str, object] = {
        "event_id": "event-1",
        "profile_id": "profile-assessment",
        "graph_version": "ai-course-v1",
        "concept_ids": ("ml.optimization.gradient-descent",),
        "correct": True,
        "response_time_ms": 1000,
        "hint_count": 0,
        "attempt_count": 1,
        "timestamp": datetime(2026, 7, 30, 8, tzinfo=UTC),
    }
    payload.update(overrides)
    return AssessmentEvent.model_validate(payload)

def test_default_parameters_and_first_observations() -> None:
    params = BktParameters()
    assert params.p_l0 == pytest.approx(0.2)
    assert update_bkt_probability(params.p_l0, True, params) == pytest.approx(0.5764705882)
    assert update_bkt_probability(params.p_l0, False, params) == pytest.approx(0.1272727273)

def test_parameters_reject_invalid_probability_combinations() -> None:
    with pytest.raises(ValidationError):
        BktParameters(p_l0=1.1)
    with pytest.raises(ValidationError, match="guess and slip"):
        BktParameters(p_guess=0.9, p_slip=0.1)

def test_repeated_correct_answers_increase_and_wrong_answers_decrease() -> None:
    params = BktParameters()
    correct = params.p_l0
    wrong = params.p_l0
    correct_values = []
    wrong_values = []
    for _ in range(4):
        correct = update_bkt_probability(correct, True, params)
        wrong = update_bkt_probability(wrong, False, params)
        correct_values.append(correct)
        wrong_values.append(wrong)
    assert correct_values == sorted(correct_values)
    assert wrong_values == sorted(wrong_values, reverse=True)
    assert all(0 <= value <= 1 for value in (*correct_values, *wrong_values))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest tests/unit/assessment/test_bkt.py -q`
Expected: FAIL because `skillforge_kb.assessment.bkt` does not yet exist.

- [ ] **Step 3: Implement the minimal parameter model and formula**

Implement `BktParameters` as a frozen Pydantic model with `Field(ge=0, le=1)` for each probability and an `after` validator rejecting `p_guess + p_slip >= 1`. Implement `update_bkt_probability` using:

```python
posterior = (
    p * (1 - params.p_slip)
    if correct
    else p * params.p_slip
) / (
    p * (1 - params.p_slip) + (1 - p) * params.p_guess
    if correct
    else p * params.p_slip + (1 - p) * (1 - params.p_guess)
)
return posterior + (1 - posterior) * params.p_transition
```

Clamp `prior_mastery`, `posterior`, and the return value; raise `ValueError` if a denominator is zero.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pytest tests/unit/assessment/test_bkt.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/assessment/test_bkt.py src/skillforge_kb/assessment/bkt.py
git commit -m "feat: add pure BKT probability updater"
```

### Task 2: BKT 事件适配与账本更新

**Files:**
- Modify: `tests/unit/assessment/test_bkt.py`
- Modify: `src/skillforge_kb/assessment/bkt.py`

**Interfaces:**
- Create frozen `BktState(mastery_probability, evidence_count, last_observed_at)`。
- Create frozen `BktAssessmentUpdateResult` with `ledger`, `model_version`, `parameter_version`, `applied`, `affected_concept_ids`, `mastery_before`, `mastery_after`, `classified_error_kind`, `reason_codes`。
- Implement `apply_bkt_event(catalog, ledger, event, parameters=None)`。

- [ ] **Step 1: Write the failing integration tests**

```python
def test_bkt_event_updates_mastery_and_is_idempotent(catalog, ledger, event_factory) -> None:
    event = event_factory(event_id="bkt-1", correct=True, evidence_refs=("item-1",))
    first = apply_bkt_event(catalog, ledger, event)
    second = apply_bkt_event(catalog, first.ledger, event)
    assert first.applied is True
    assert first.mastery_before == ((event.concept_ids[0], 0.2),)
    assert first.mastery_after[0][1] == pytest.approx(0.5764705882)
    assert first.model_version == "bkt.v1"
    assert first.reason_codes == ("bkt_update_applied",)
    assert second.applied is False
    assert second.reason_codes == ("duplicate_event",)

def test_bkt_event_preserves_unrelated_mastery_and_updates_errors(catalog, ledger, event_factory) -> None:
    wrong = event_factory(event_id="bkt-wrong", correct=False, hint_count=2)
    result = apply_bkt_event(catalog, ledger, wrong)
    assert result.classified_error_kind.value == "concept_confusion"
    assert result.ledger.profile.error_patterns[0].count == 1

@pytest.mark.parametrize("field", ["profile_id", "graph_version", "concept_ids"])
def test_bkt_event_scope_failures_do_not_mutate_ledger(catalog, ledger, event_factory, field) -> None:
    values = {
        "profile_id": "wrong-profile",
        "graph_version": "wrong-graph",
        "concept_ids": ("unknown.concept",),
    }
    with pytest.raises(ValueError):
        apply_bkt_event(catalog, ledger, event_factory(**{field: values[field]}))
    assert ledger.processed_event_ids == ()
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest tests/unit/assessment/test_bkt.py -q`
Expected: FAIL because state/result models and `apply_bkt_event` are missing.

- [ ] **Step 3: Implement event adapter**

Inside `bkt.py`, validate `BktParameters`, `AssessmentLedger`, and `AssessmentEvent` from `model_dump()`. Reuse the scope checks and error helpers from `update.py` through private imports or small shared helpers. For each concept, use existing `mastery_score` when present, otherwise `parameters.p_l0`; call `update_bkt_probability`; create `KnowledgeMastery(assessment_status=ASSESSED, confidence=existing.confidence or 0.25, observed_at=event.timestamp, evidence_refs=unique refs)`. Preserve unrelated mastery and update `error_patterns` with the existing classifier. Append the event ID to the ledger only after all validations pass.

On duplicate IDs return the original ledger, empty affected facts, `applied=False`, and `reason_codes=("duplicate_event",)`. Return `BktAssessmentUpdateResult` with model and parameter versions for both applied and duplicate results.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pytest tests/unit/assessment/test_bkt.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/assessment/test_bkt.py src/skillforge_kb/assessment/bkt.py
git commit -m "feat: apply BKT updates to assessment events"
```

### Task 3: Public exports and regression coverage

**Files:**
- Modify: `src/skillforge_kb/assessment/__init__.py`
- Modify: `tests/unit/assessment/test_bkt.py`
- Test: `tests/unit/assessment/test_update.py`

**Interfaces:**
- Re-export `BktParameters`, `BktState`, `BktAssessmentUpdateResult`, `apply_bkt_event`, and `update_bkt_probability` from `skillforge_kb.assessment`。

- [ ] **Step 1: Write the failing export and regression tests**

```python
def test_bkt_symbols_are_public() -> None:
    from skillforge_kb.assessment import BktParameters, apply_bkt_event
    assert BktParameters().model_version == "bkt.v1"
    assert callable(apply_bkt_event)

def test_rule_based_update_remains_unchanged(catalog, ledger, event_factory) -> None:
    result = apply_assessment_event(catalog, ledger, event_factory(correct=True))
    assert result.policy_version == "rule-based-assessment.v1"
    assert result.mastery_after[0][1] == pytest.approx(0.56)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/assessment/test_bkt.py::test_bkt_symbols_are_public -q`
Expected: FAIL until exports are added.

- [ ] **Step 3: Add exports without changing default strategy**

Add imports and names to `src/skillforge_kb/assessment/__init__.py`. Do not modify the body or default parameters of `apply_assessment_event`.

- [ ] **Step 4: Run focused and regression tests**

Run: `pytest tests/unit/assessment/test_bkt.py tests/unit/assessment/test_update.py -q`
Expected: PASS with all existing rule-based assertions unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/assessment/__init__.py tests/unit/assessment/test_bkt.py
git commit -m "feat: export BKT assessment strategy"
```

### Task 4: Full verification and handoff

**Files:**
- No production changes; inspect `src/skillforge_kb/platform/graph.py` and `src/skillforge_kb/planning/planner.py` for accidental default-path changes.

- [ ] **Step 1: Run the complete assessment and planning suites**

Run: `pytest tests/unit/assessment tests/unit/planning tests/unit/platform/test_graph.py -q`
Expected: PASS; existing path generation remains rule-based.

- [ ] **Step 2: Run the complete unit suite**

Run: `pytest tests/unit -q`
Expected: PASS, or document unrelated pre-existing failures with file and error.

- [ ] **Step 3: Inspect the diff and status**

Run: `git diff HEAD~3..HEAD -- src/skillforge_kb/assessment tests/unit/assessment` and `git status --short`.
Expected: only BKT module, assessment exports, and focused tests are changed by this plan; pre-existing unrelated worktree files remain untouched.

- [ ] **Step 4: Commit verification notes if needed**

Only commit additional notes when a test exposes a required compatibility fix; otherwise leave the verification output in the handoff summary.
