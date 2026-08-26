# 知识追踪预测快照存储实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在平台测评流程中持久化答题前预测概率，使真实 rule/BKT 事件可被离线评估器消费。

**Architecture:** 扩展 `PlatformRunRepository` Protocol 和内存实现，按 `(run_id, assessment_id)` 保存 `KnowledgeTracingObservation`。`PlatformService.submit_assessment` 在更新成功后写入 observation；旧运行结果和画像协议保持不变。

**Tech Stack:** Python 3.12、Pydantic v2、pytest、现有 InMemoryPlatformRunRepository 和 evaluation 模块。

## Global Constraints

- 不修改 `PlatformRunResult`、`LearnerProfileSnapshot` JSON 结构。
- observation ID 必须等于 assessment ID。
- 重复 payload 不重复写 observation；不同 payload 抛出冲突。
- 更新器失败不得写 observation。
- 所有新增生产代码必须先有已验证失败的测试。

---

### Task 1: Repository observation 存储

**Files:**
- Modify: `tests/unit/platform/test_repository.py`
- Modify: `src/skillforge_kb/platform/ports.py`
- Modify: `src/skillforge_kb/platform/repository.py`

**Interfaces:**
- `get_prediction_observation(run_id, assessment_id) -> KnowledgeTracingObservation | None`。
- `save_prediction_observation(run_id, assessment_id, observation) -> None`。
- `list_prediction_observations(run_id) -> tuple[KnowledgeTracingObservation, ...]`。

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, datetime
from skillforge_kb.evaluation.knowledge_tracing import KnowledgeTracingObservation

def _observation(assessment_id="assessment-1", probability=0.2):
    return KnowledgeTracingObservation(
        observation_id=assessment_id,
        profile_id="profile-assessment",
        concept_id="ml.optimization.gradient-descent",
        model_version="bkt.v1",
        predicted_mastery=probability,
        correct=True,
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )

def test_repository_stores_and_lists_observations(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="observation-run")
    repository.reserve(request)
    observation = _observation()
    repository.save_prediction_observation(build_run_id(request), "assessment-1", observation)
    assert repository.get_prediction_observation(build_run_id(request), "assessment-1") == observation
    assert repository.list_prediction_observations(build_run_id(request)) == (observation,)

def test_repository_rejects_observation_conflicts(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="observation-conflict")
    repository.reserve(request)
    run_id = build_run_id(request)
    repository.save_prediction_observation(run_id, "assessment-1", _observation())
    with pytest.raises(ValueError, match="different observation"):
        repository.save_prediction_observation(
            run_id, "assessment-1", _observation(probability=0.8)
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_repository.py -q`
Expected: FAIL because observation methods do not exist.

- [ ] **Step 3: Implement Protocol and memory storage**

Import `KnowledgeTracingObservation` in `ports.py` and add the three methods. In `InMemoryPlatformRunRepository`, add `_observations: dict[tuple[str, str], KnowledgeTracingObservation]`; validate run existence, observation ID equality, profile identity, and model data. On existing key, compare serialized observations and raise `ValueError("assessment has a different observation")` when different. List observations in insertion order for the requested run.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/platform/test_repository.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/platform/ports.py src/skillforge_kb/platform/repository.py tests/unit/platform/test_repository.py
git commit -m "feat: persist platform knowledge tracing observations"
```

### Task 2: Platform measurement snapshot

**Files:**
- Modify: `tests/unit/platform/test_graph.py`
- Modify: `src/skillforge_kb/platform/graph.py`

**Interfaces:**
- No public method changes; `submit_assessment` writes observation through the repository.

- [ ] **Step 1: Write failing platform tests**

Add tests using the existing `platform_case` fixture and `_service` helper:

```python
def test_rule_assessment_records_prior_mastery(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(PlatformRunRequest(profile=profile, idempotency_key="obs-rule"))
    concept_id = initial.planning.current_node.concept_id
    service.submit_assessment(initial.run_id, {
        "assessment_id": "obs-rule-1", "concept_id": concept_id, "score": 1.0,
        "response_time_ms": 1000, "hint_count": 0, "attempt_count": 1,
    })
    observation = service._repository.get_prediction_observation(initial.run_id, "obs-rule-1")
    assert observation is not None
    assert observation.model_version == "rule.v1"
    assert observation.predicted_mastery == 0.50

def test_bkt_assessment_records_bkt_prior_and_replay_is_idempotent(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(PlatformRunRequest(profile=profile, idempotency_key="obs-bkt", assessment_model=AssessmentModel.BKT))
    concept_id = initial.planning.current_node.concept_id
    submission = {"assessment_id": "obs-bkt-1", "concept_id": concept_id, "score": 1.0, "response_time_ms": 1000, "hint_count": 0, "attempt_count": 1}
    first = service.submit_assessment(initial.run_id, submission)
    replay = service.submit_assessment(initial.run_id, submission)
    observation = service._repository.get_prediction_observation(initial.run_id, "obs-bkt-1")
    assert replay == first
    assert observation is not None
    assert observation.model_version == "bkt.v1"
    assert observation.predicted_mastery == 0.20
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_graph.py -q -k observation`
Expected: FAIL because submit_assessment does not create observations.

- [ ] **Step 3: Implement snapshot creation and persistence**

Before creating `AssessmentEvent`, derive `prior_mastery` from `request.profile.knowledge_mastery`; use `0.50` for rule and `BktParameters().p_l0` for BKT. Capture the event timestamp in a local variable, use it for both event and observation, and derive `model_version` from `request.assessment_model`. After the existing successful `save`/`save_assessment` branches, call `save_prediction_observation` once. Do not write on exceptions.

- [ ] **Step 4: Run platform tests**

Run: `pytest tests/unit/platform/test_graph.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/platform/graph.py tests/unit/platform/test_graph.py
git commit -m "feat: record assessment prediction snapshots"
```

### Task 3: Observation export and regression

**Files:**
- Modify: `tests/unit/platform/test_repository.py`
- Modify: `tests/unit/integration/test_three_agent_platform_flow.py`

- [ ] **Step 1: Write export regression test**

```python
def test_saved_observations_feed_knowledge_tracing_evaluation(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(PlatformRunRequest(profile=profile, idempotency_key="obs-export"))
    concept_id = initial.planning.current_node.concept_id
    service.submit_assessment(initial.run_id, {
        "assessment_id": "obs-export-1", "concept_id": concept_id, "score": 1.0,
        "response_time_ms": 1000, "hint_count": 0, "attempt_count": 1,
    })
    observations = service._repository.list_prediction_observations(initial.run_id)
    report = evaluate_knowledge_tracing(observations)
    assert report.metrics.sample_count == 1
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/platform/test_repository.py tests/unit/platform/test_graph.py -q -k observation`
Expected: FAIL until the platform writes snapshots.

- [ ] **Step 3: Run complete focused regression**

Run: `pytest tests/unit/assessment tests/unit/evaluation tests/unit/platform tests/unit/integration/test_three_agent_platform_flow.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/platform/test_repository.py tests/unit/integration/test_three_agent_platform_flow.py
git commit -m "test: verify prediction snapshot evaluation export"
```

### Task 4: Final verification

- [ ] **Step 1: Run lint**

Run: `ruff check src/skillforge_kb/platform/ports.py src/skillforge_kb/platform/repository.py src/skillforge_kb/platform/graph.py tests/unit/platform/test_repository.py tests/unit/platform/test_graph.py`
Expected: no lint errors.

- [ ] **Step 2: Run focused suites**

Run: `pytest tests/unit/assessment tests/unit/evaluation tests/unit/platform -q`
Expected: PASS.

- [ ] **Step 3: Inspect status**

Run: `git status --short` and `git diff HEAD~3..HEAD --stat`.
Expected: only observation storage files changed by this plan; unrelated worktree files remain untouched.
