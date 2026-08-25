# 知识追踪离线评估实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 rule 与 BKT 预测概率提供统一的 Brier、LogLoss、AUC 离线评估和可审计比较报告。

**Architecture:** 新增 `evaluation/knowledge_tracing.py`，使用冻结 Pydantic 模型承载观测、指标、报告和比较结果。指标计算使用纯 Python 确定性函数，不依赖 sklearn；evaluation 包通过 `__init__.py` 暴露公共接口。

**Tech Stack:** Python 3.12、Pydantic v2、pytest、现有 evaluation 序列化规范。

## Global Constraints

- 只评估调用方提供的答题前预测概率，不重放线上事件。
- 不修改 `AssessmentLedger`、BKT 更新器或平台 API。
- 概率输入限制在 `[0,1]`，LogLoss 计算使用 `1e-15` 数值保护。
- AUC 只有正负样本同时存在时才计算。
- 所有新增生产代码必须先有已验证失败的测试。

---

### Task 1: 观测、指标和基础计算

**Files:**
- Create: `tests/unit/evaluation/test_knowledge_tracing.py`
- Create: `src/skillforge_kb/evaluation/knowledge_tracing.py`

**Interfaces:**
- `KnowledgeTracingObservation`：`observation_id`、`profile_id`、`concept_id`、`model_version`、`predicted_mastery`、`correct`、`observed_at`。
- `KnowledgeTracingMetrics`：`sample_count`、`positive_count`、`negative_count`、`brier_score`、`log_loss`、`auc`。
- `evaluate_knowledge_tracing(observations, *, model_version=None, data_version="knowledge-tracing-eval.v1")`。

- [ ] **Step 1: Write the failing tests**

```python
from datetime import UTC, datetime
import pytest
from pydantic import ValidationError
from skillforge_kb.evaluation.knowledge_tracing import (
    KnowledgeTracingObservation,
    evaluate_knowledge_tracing,
)

def _observation(observation_id: str, probability: float, correct: bool, model="bkt.v1"):
    return KnowledgeTracingObservation(
        observation_id=observation_id,
        profile_id="profile-eval",
        concept_id="ml.optimization.gradient-descent",
        model_version=model,
        predicted_mastery=probability,
        correct=correct,
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )

def test_metrics_match_known_predictions() -> None:
    report = evaluate_knowledge_tracing((
        _observation("o1", 0.9, True),
        _observation("o2", 0.2, False),
        _observation("o3", 0.8, True),
        _observation("o4", 0.1, False),
    ))
    assert report.metrics.sample_count == 4
    assert report.metrics.brier_score == pytest.approx(0.025)
    assert report.metrics.log_loss == pytest.approx(
        -(2 * __import__("math").log(0.9) + 2 * __import__("math").log(0.8)) / 4
    )
    assert report.metrics.auc == pytest.approx(1.0)

def test_single_class_auc_is_none_and_invalid_input_fails() -> None:
    report = evaluate_knowledge_tracing((_observation("o1", 0.8, True),))
    assert report.metrics.auc is None
    with pytest.raises(ValidationError):
        _observation("bad", 1.1, True)
    with pytest.raises(ValueError, match="at least one"):
        evaluate_knowledge_tracing(())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/evaluation/test_knowledge_tracing.py -q`
Expected: FAIL because the module and models do not exist.

- [ ] **Step 3: Implement models and metrics**

Implement frozen Pydantic models with `extra="forbid"`; validate timezone-aware timestamps and unique IDs in `evaluate_knowledge_tracing`. Infer the model version when omitted and reject mixed versions. Compute:

```python
brier = sum((p - int(y)) ** 2 for p, y in pairs) / n
safe_p = min(1 - 1e-15, max(1e-15, p))
log_loss = -sum(y * log(safe_p) + (1-y) * log(1-safe_p) for p, y in pairs) / n
```

Implement `_roc_auc` by sorting `(probability, label)` ascending, assigning average ranks to ties, and calculating the Mann–Whitney form `(rank_sum_positive - pos*(pos+1)/2)/(pos*neg)`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/evaluation/test_knowledge_tracing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/evaluation/knowledge_tracing.py tests/unit/evaluation/test_knowledge_tracing.py
git commit -m "feat: add knowledge tracing evaluation metrics"
```

### Task 2: 报告、digest 和比较

**Files:**
- Modify: `tests/unit/evaluation/test_knowledge_tracing.py`
- Modify: `src/skillforge_kb/evaluation/knowledge_tracing.py`

**Interfaces:**
- `KnowledgeTracingEvaluationReport`：包含 schema、data_version、model_version、observations、metrics、disclaimer、report_digest。
- `KnowledgeTracingComparison`：包含 data_version、observation_ids、ranking、metric_deltas。
- `compare_knowledge_tracing_reports(reports)`。
- `write_knowledge_tracing_report(report, output_path)` 和 `load_knowledge_tracing_report(path)`，采用现有临时文件替换模式。

- [ ] **Step 1: Write failing report tests**

```python
def test_report_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    report = evaluate_knowledge_tracing((_observation("o1", 0.8, True),))
    output = tmp_path / "kt-report.json"
    write_knowledge_tracing_report(report, output)
    assert load_knowledge_tracing_report(output) == report
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["metrics"]["brier_score"] = 0.9
    output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="digest"):
        load_knowledge_tracing_report(output)

def test_comparison_requires_same_observation_set() -> None:
    bkt = evaluate_knowledge_tracing((
        _observation("o1", 0.9, True, "bkt.v1"),
        _observation("o2", 0.2, False, "bkt.v1"),
    ))
    rule = evaluate_knowledge_tracing((
        _observation("o1", 0.7, True, "rule.v1"),
        _observation("o2", 0.4, False, "rule.v1"),
    ))
    comparison = compare_knowledge_tracing_reports((bkt, rule))
    assert comparison.ranking[0] in {"bkt.v1", "rule.v1"}
    with pytest.raises(ValueError, match="observation IDs"):
        compare_knowledge_tracing_reports((
            bkt,
            evaluate_knowledge_tracing((_observation("different", 0.5, True, "rule.v1"),)),
        ))
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/unit/evaluation/test_knowledge_tracing.py -q`
Expected: FAIL because report serialization and comparison are missing.

- [ ] **Step 3: Implement report and comparison**

Build `report_digest` from `model_dump(mode="json", exclude={"report_digest"})` with canonical sorted JSON and prefix `knowledge_tracing_evaluation_`. Validate digest and metric reconstruction in the report model. For comparison, require at least two reports, matching `data_version` and ordered observation ID sets; rank by `(brier_score, log_loss, model_version)` ascending and include per-model deltas against the first-ranked model.

Use an atomic writer that writes `.<name>.tmp`, replaces the destination, and removes the temporary file on `OSError`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/unit/evaluation/test_knowledge_tracing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/evaluation/knowledge_tracing.py tests/unit/evaluation/test_knowledge_tracing.py
git commit -m "feat: add knowledge tracing evaluation reports"
```

### Task 3: 公共导出与 evaluation 回归

**Files:**
- Modify: `src/skillforge_kb/evaluation/__init__.py`
- Modify: `tests/unit/evaluation/test_serialization.py`

- [ ] **Step 1: Write the failing public import test**

```python
def test_knowledge_tracing_evaluation_is_public() -> None:
    from skillforge_kb.evaluation import evaluate_knowledge_tracing
    assert callable(evaluate_knowledge_tracing)
```

- [ ] **Step 2: Run test and verify RED**

Run: `pytest tests/unit/evaluation/test_serialization.py::test_knowledge_tracing_evaluation_is_public -q`
Expected: FAIL until exports are added.

- [ ] **Step 3: Add exports**

Re-export all public models, functions, writer and loader from `evaluation/__init__.py`; do not alter existing exports.

- [ ] **Step 4: Run evaluation regression**

Run: `pytest tests/unit/evaluation -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skillforge_kb/evaluation/__init__.py tests/unit/evaluation/test_serialization.py
git commit -m "feat: export knowledge tracing evaluation"
```

### Task 4: 最终验证

- [ ] **Step 1: Run lint**

Run: `ruff check src/skillforge_kb/evaluation/knowledge_tracing.py src/skillforge_kb/evaluation/__init__.py tests/unit/evaluation/test_knowledge_tracing.py`
Expected: no lint errors.

- [ ] **Step 2: Run evaluation and assessment suites**

Run: `pytest tests/unit/evaluation tests/unit/assessment -q`
Expected: PASS.

- [ ] **Step 3: Inspect status and diff**

Run: `git status --short` and `git diff HEAD~3..HEAD --stat`.
Expected: only knowledge-tracing evaluation files changed by this plan; unrelated worktree files remain untouched.
