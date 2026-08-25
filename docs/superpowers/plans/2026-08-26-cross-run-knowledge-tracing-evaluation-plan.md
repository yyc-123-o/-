# 跨运行知识追踪评估实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 聚合学生多个运行的 prediction observations，按模型生成评估报告，并通过只读 API 提供结果。

**Architecture:** repository 按 profile 过滤并稳定排序 observation；evaluation 新增按 `model_version` 分组的纯函数；PlatformService 暴露学生级读取方法；FastAPI 增加 `/api/v1/profiles/{profile_id}/knowledge-tracing/evaluation`。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、pytest、现有 repository/evaluation 模型。

## Global Constraints

- 聚合读取不修改运行状态或 repository。
- 不同模型数据只分别评估，不自动配对比较。
- profile 之间严格隔离；无 observation 返回明确错误。
- API 遵循现有 `/api/v1` 路由和错误格式。
- 新增生产代码必须先有失败测试。

---

### Task 1: Repository 聚合与 evaluation 分组

**Files:**
- Modify: `tests/unit/platform/test_repository.py`
- Modify: `src/skillforge_kb/platform/ports.py`
- Modify: `src/skillforge_kb/platform/repository.py`
- Modify: `tests/unit/evaluation/test_knowledge_tracing.py`
- Modify: `src/skillforge_kb/evaluation/knowledge_tracing.py`

**Interfaces:**
- `list_prediction_observations_for_profile(profile_id, *, model_version=None)`。
- `evaluate_knowledge_tracing_by_model(observations, *, data_version=...)`。

- [ ] **Step 1: Write failing tests**

```python
def test_repository_lists_profile_observations_across_runs_and_filters_model(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    first = PlatformRunRequest(profile=profile, idempotency_key="aggregate-1")
    second = PlatformRunRequest(profile=profile, idempotency_key="aggregate-2")
    repository.reserve(first)
    repository.reserve(second)
    repository.save_prediction_observation(build_run_id(second), "b", _observation("b", 0.4))
    repository.save_prediction_observation(build_run_id(first), "a", _observation("a", 0.6))
    assert tuple(item.observation_id for item in repository.list_prediction_observations_for_profile(profile.profile_id)) == ("a", "b")
    assert repository.list_prediction_observations_for_profile(profile.profile_id, model_version="bkt.v1")[0].observation_id == "a"

def test_evaluate_knowledge_tracing_by_model_returns_sorted_reports() -> None:
    reports = evaluate_knowledge_tracing_by_model((
        _observation("r", 0.6, model="rule.v1"),
        _observation("b", 0.7, model="bkt.v1"),
    ))
    assert tuple(report.model_version for report in reports) == ("bkt.v1", "rule.v1")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_repository.py tests/unit/evaluation/test_knowledge_tracing.py -q`
Expected: FAIL because aggregation methods do not exist.

- [ ] **Step 3: Implement aggregation**

Add the Protocol method and implement profile filtering by `_requests`; sort `(observation.observed_at, run_id, observation.observation_id)`. Add `evaluate_knowledge_tracing_by_model` using a dictionary keyed by model version, call the existing evaluator per group, and return reports sorted by model version. Reject empty input.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/platform/test_repository.py tests/unit/evaluation/test_knowledge_tracing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/platform/ports.py src/skillforge_kb/platform/repository.py src/skillforge_kb/evaluation/knowledge_tracing.py tests/unit/platform/test_repository.py tests/unit/evaluation/test_knowledge_tracing.py
git commit -m "feat: aggregate knowledge tracing observations by profile"
```

### Task 2: PlatformService 学生级评估入口

**Files:**
- Modify: `tests/unit/platform/test_graph.py`
- Modify: `src/skillforge_kb/platform/graph.py`

**Interfaces:**
- `PlatformService.evaluate_profile_knowledge_tracing(profile_id) -> tuple[KnowledgeTracingEvaluationReport, ...]`。

- [ ] **Step 1: Write failing service tests**

```python
from datetime import UTC, datetime
from skillforge_kb.evaluation.knowledge_tracing import KnowledgeTracingObservation

def _profile_observation(profile_id: str, observation_id: str) -> KnowledgeTracingObservation:
    return KnowledgeTracingObservation(
        observation_id=observation_id,
        profile_id=profile_id,
        concept_id="math.linear-algebra.scalar",
        model_version="rule.v1",
        predicted_mastery=0.5,
        correct=True,
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )

def test_service_evaluates_profile_observations(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    run = service.run(PlatformRunRequest(profile=profile, idempotency_key="eval-entry"))
    service._repository.save_prediction_observation(
        run.run_id,
        "eval-1",
        _profile_observation(profile.profile_id, "eval-1"),
    )
    reports = service.evaluate_profile_knowledge_tracing(profile.profile_id)
    assert len(reports) == 1
    assert reports[0].metrics.sample_count == 1

def test_service_evaluation_rejects_profile_without_observations(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    with pytest.raises(ValueError, match="no prediction observations"):
        service.evaluate_profile_knowledge_tracing(profile.profile_id)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_graph.py -q -k profile_observations`
Expected: FAIL because the service method is missing.

- [ ] **Step 3: Implement service method**

Import `evaluate_knowledge_tracing_by_model`; fetch `self._repository.list_prediction_observations_for_profile(profile_id)`, raise the specified ValueError when empty, and return grouped reports. Do not acquire a new write lock or mutate state; the existing service lock may guard the read.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/platform/test_graph.py -q -k profile_observations`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/platform/graph.py tests/unit/platform/test_graph.py
git commit -m "feat: expose profile knowledge tracing evaluation"
```

### Task 3: API 只读端点

**Files:**
- Modify: `tests/unit/api/conftest.py`
- Modify: `tests/unit/api/test_app.py`
- Modify: `src/skillforge_kb/api/app.py`

**Interfaces:**
- `GET /api/v1/profiles/{profile_id}/knowledge-tracing/evaluation` returns `list[KnowledgeTracingEvaluationReport]`。

- [ ] **Step 1: Write failing API tests**

Extend the stub service with `evaluate_profile_knowledge_tracing`; add tests for a 200 response containing report JSON and a 404 response when the stub raises `ValueError("no prediction observations")`.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/api/test_app.py -q -k knowledge_tracing`
Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement route**

Add a Protocol method to the API service interface, register the GET route with `response_model=list[KnowledgeTracingEvaluationReport]`, call the service method, and translate the no-observation ValueError to HTTP 404 with detail code `knowledge_tracing_not_found`. Preserve existing exception handlers.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/api/test_app.py -q -k knowledge_tracing`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/api/app.py tests/unit/api/conftest.py tests/unit/api/test_app.py
git commit -m "feat: add knowledge tracing evaluation API"
```

### Task 4: Final verification

- [ ] **Step 1: Run lint**

Run: `ruff check src/skillforge_kb/evaluation/knowledge_tracing.py src/skillforge_kb/platform/ports.py src/skillforge_kb/platform/repository.py src/skillforge_kb/platform/graph.py src/skillforge_kb/api/app.py tests/unit/evaluation/test_knowledge_tracing.py tests/unit/platform/test_repository.py tests/unit/platform/test_graph.py tests/unit/api/test_app.py tests/unit/api/conftest.py`
Expected: no lint errors.

- [ ] **Step 2: Run focused suites**

Run: `pytest tests/unit/evaluation tests/unit/assessment tests/unit/platform tests/unit/api -q`
Expected: PASS.

- [ ] **Step 3: Inspect status and diff**

Run: `git status --short` and `git diff HEAD~3..HEAD --stat`.
Expected: only cross-run aggregation and API files changed by this plan; unrelated worktree files remain untouched.
