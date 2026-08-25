# BKT 平台测评接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让平台请求显式选择 `rule` 或 `bkt` 测评模型，并在 BKT 模式下完成测评更新、重新规划和幂等闭环，同时保持规则模式兼容。

**Architecture:** 在 `platform/models.py` 增加 `AssessmentModel` 和 `PlatformRunRequest.assessment_model`，默认 `rule`。在 `PlatformService.submit_assessment` 构造事件后按模型分派到 `apply_assessment_event` 或 `apply_bkt_event`；两个更新器只通过 `ledger.profile` 与平台衔接，规划器本身不改。

**Tech Stack:** Python 3.12、Pydantic v2、pytest、现有 PlatformService/InMemoryRepository。

## Global Constraints

- 缺失 `assessment_model` 的旧请求必须继续解析为 `rule`。
- `build_run_id` 仍只由 profile 与幂等键决定；`build_request_digest` 必须包含测评模型。
- `rule` 默认行为和现有断言数值不得改变。
- BKT 失败不得静默 fallback 到 rule。
- 所有生产修改前必须有已验证失败的测试。

---

### Task 1: 请求模型与摘要选择

**Files:**
- Modify: `tests/unit/platform/test_models.py`
- Modify: `src/skillforge_kb/platform/models.py`

**Interfaces:**
- 新增 `AssessmentModel(StrEnum)`，成员 `RULE="rule"`、`BKT="bkt"`。
- `PlatformRunRequest.assessment_model: AssessmentModel = AssessmentModel.RULE`。

- [ ] **Step 1: Write the failing tests**

```python
from pydantic import ValidationError
from skillforge_kb.platform.models import AssessmentModel

def test_assessment_model_defaults_to_rule(profile) -> None:
    request = PlatformRunRequest(profile=profile, idempotency_key="model-default")
    assert request.assessment_model is AssessmentModel.RULE

def test_bkt_model_changes_request_digest_but_not_run_id(profile) -> None:
    rule = PlatformRunRequest(profile=profile, idempotency_key="model-digest")
    bkt = rule.model_copy(update={"assessment_model": AssessmentModel.BKT})
    assert build_request_digest(rule) != build_request_digest(bkt)
    assert build_run_id(rule) == build_run_id(bkt)

def test_invalid_assessment_model_is_rejected(profile) -> None:
    with pytest.raises(ValidationError):
        PlatformRunRequest(
            profile=profile,
            idempotency_key="model-invalid",
            assessment_model="unsupported",
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_models.py -q`
Expected: FAIL because `AssessmentModel` and the request field do not exist.

- [ ] **Step 3: Implement the model field**

Add the enum near `ExecutionMode` and add the defaulted field to `PlatformRunRequest`. Do not change `build_run_id`; its existing payload remains profile ID plus idempotency key.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/platform/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/platform/models.py tests/unit/platform/test_models.py
git commit -m "feat: add explicit assessment model to platform requests"
```

### Task 2: 平台测评分派

**Files:**
- Modify: `tests/unit/platform/test_graph.py`
- Modify: `src/skillforge_kb/platform/graph.py`

**Interfaces:**
- `submit_assessment` 保持现有参数和返回类型。
- `request.assessment_model is AssessmentModel.BKT` 时调用 `apply_bkt_event`；其他情况调用 `apply_assessment_event`。

- [ ] **Step 1: Write the failing dispatch tests**

```python
from pathlib import Path
import skillforge_kb.platform.graph as graph_module

def test_bkt_assessment_dispatches_to_bkt_updater(monkeypatch) -> None:
    project_root = Path(__file__).parents[3]
    service = build_default_platform_service(project_root)
    initial_run = service.run(
        PlatformRunRequest(
            profile=_empty_profile(),
            idempotency_key="dispatch-bkt-run",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
            assessment_model=AssessmentModel.BKT,
        )
    )
    calls: list[str] = []
    original = graph_module.apply_bkt_event

    def capture(catalog, ledger, event, parameters=None):
        calls.append("bkt")
        return original(catalog, ledger, event, parameters)

    monkeypatch.setattr(graph_module, "apply_bkt_event", capture)
    result = service.submit_assessment(
        initial_run.run_id,
        {
            "assessment_id": "dispatch-bkt-1",
            "concept_id": initial_run.planning.current_node.concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )
    assert result.status is PlatformRunStatus.COMPLETED
    assert calls == ["bkt"]
```

Also add a rule-mode test asserting a monkeypatched `apply_assessment_event` is called and the existing mastery result remains `0.56`.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_graph.py -q`
Expected: FAIL because the platform always calls the rule updater and does not import `apply_bkt_event`.

- [ ] **Step 3: Implement explicit dispatch**

Import `AssessmentModel`, `apply_bkt_event`, and keep `apply_assessment_event`. Replace the single update call with:

```python
if request.assessment_model is AssessmentModel.BKT:
    update = apply_bkt_event(self._dependencies.catalog, AssessmentLedger(profile=request.profile), event)
else:
    update = apply_assessment_event(self._dependencies.catalog, AssessmentLedger(profile=request.profile), event)
```

Keep all subsequent request refresh, failure handling, completion, and repository writes unchanged. Do not catch BKT errors to fallback.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/platform/test_graph.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/platform/graph.py tests/unit/platform/test_graph.py
git commit -m "feat: dispatch platform assessments to BKT"
```

### Task 3: BKT 平台闭环与回归

**Files:**
- Modify: `tests/unit/integration/test_three_agent_platform_flow.py`
- Modify: `tests/unit/platform/test_models.py` if additional identity assertions are needed

**Interfaces:**
- No new public methods; verify the existing `run` and `submit_assessment` flow.

- [ ] **Step 1: Write the failing BKT flow tests**

Add tests using the existing `build_default_platform_service` and an empty `LearnerProfileSnapshot` created by:

```python
def _empty_profile() -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-BKT-FLOW-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
```

```python
def test_bkt_assessment_updates_mastery_and_replans() -> None:
    project_root = Path(__file__).parents[3]
    service = build_default_platform_service(project_root)
    profile = _empty_profile()
    request = PlatformRunRequest(
        profile=profile,
        idempotency_key="assessment-bkt-flow",
        execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        assessment_model=AssessmentModel.BKT,
    )
    initial = service.run(request)
    concept_id = initial.planning.current_node.concept_id
    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "assessment-bkt-flow-1",
            "concept_id": concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )
    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id != concept_id
```

Add an incorrect-answer BKT test asserting the current node remains selected and a duplicate submission test asserting identical results.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/integration/test_three_agent_platform_flow.py -q -k bkt`
Expected: FAIL because request construction and platform dispatch are not implemented yet.

- [ ] **Step 3: Run the complete focused regression set**

Run: `pytest tests/unit/assessment tests/unit/platform tests/unit/planning -q`
Expected: PASS with existing rule assertions unchanged.

- [ ] **Step 4: Run the BKT integration tests**

Run: `pytest tests/unit/integration/test_three_agent_platform_flow.py -q -k bkt`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/integration/test_three_agent_platform_flow.py tests/unit/platform/test_models.py
git commit -m "test: cover BKT platform learning flow"
```

### Task 4: Verification and handoff

**Files:**
- Inspect only; no unrelated cleanup.

- [ ] **Step 1: Run lint and focused tests**

Run: `ruff check src/skillforge_kb/platform/models.py src/skillforge_kb/platform/graph.py tests/unit/platform/test_models.py tests/unit/platform/test_graph.py tests/unit/integration/test_three_agent_platform_flow.py`
Expected: no lint errors.

- [ ] **Step 2: Run all non-service suites**

Run: `pytest tests/unit/assessment tests/unit/platform tests/unit/planning tests/unit/agents tests/unit/retrieval tests/unit/resources tests/unit/evaluation tests/unit/ingestion -q`
Expected: PASS; integration tests requiring external services may be excluded and documented.

- [ ] **Step 3: Inspect status and diff**

Run: `git status --short` and `git diff HEAD~3..HEAD --stat`.
Expected: only platform model/graph and focused tests changed by this plan; existing unrelated worktree files remain untouched.

- [ ] **Step 4: Commit verification-only formatting fixes if required**

```bash
git add src/skillforge_kb/platform tests/unit/platform tests/unit/integration/test_three_agent_platform_flow.py
git commit -m "style: normalize platform BKT integration"
```
