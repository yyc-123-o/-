# 跨运行知识追踪评估聚合设计

## 目标

将多个学习运行中的 prediction observation 聚合到学生级评估报告，按模型分别计算 Brier、LogLoss 和 AUC，为后续遗忘模型或参数调优提供真实基线。

## Repository 接口

在 `PlatformRunRepository` 增加：

```python
def list_prediction_observations_for_profile(
    self,
    profile_id: str,
    *,
    model_version: str | None = None,
) -> tuple[KnowledgeTracingObservation, ...]
```

内存实现遍历该 profile 的所有运行请求，收集 observation，按 `(observed_at, run_id, assessment_id)` 排序，确保跨运行结果稳定。指定 `model_version` 时只返回匹配模型；profile 不存在时返回空元组，不泄露其他学生数据。

## Evaluation 聚合函数

新增：

```python
def evaluate_knowledge_tracing_by_model(
    observations: Sequence[KnowledgeTracingObservation],
    *,
    data_version: str = "knowledge-tracing-eval.v1",
) -> tuple[KnowledgeTracingEvaluationReport, ...]
```

函数按 `model_version` 分组，组内保持观测时间顺序，分别调用 `evaluate_knowledge_tracing`，返回按模型版本升序排列的报告。空输入抛出错误；每组至少一条观测。该函数不自动调用模型比较，因为不同模型通常来自不同运行，观测 ID 不一定配对。

## PlatformService 入口

新增：

```python
def evaluate_profile_knowledge_tracing(
    self,
    profile_id: str,
) -> tuple[KnowledgeTracingEvaluationReport, ...]
```

方法从 repository 获取 profile 的全部 observation，并调用 evaluation 聚合函数。无 observation 时抛出 `ValueError("no prediction observations")`；返回结果只包含该 profile 的模型报告。该入口不改变学习运行状态，不写 repository。

## API 适配

在 `src/skillforge_kb/api/app.py` 增加只读 endpoint：

`GET /api/v1/profiles/{profile_id}/knowledge-tracing/evaluation`

响应为报告数组的 JSON；无记录返回 HTTP 404，其他校验错误返回现有错误格式。API 层只调用 PlatformService 入口，不重复实现指标。

## 数据一致性

- 同一 profile 的 observation 必须具有相同 graph version 语义（observation 当前不携带 graph version，因此由 run request profile 保证）。
- 跨运行排序按 observation 时间和稳定 ID，不能依赖字典遍历偶然顺序。
- 评估报告中的 `model_version` 与分组键一致。
- 需要配对比较时，调用方显式传入各模型报告给 `compare_knowledge_tracing_reports`；观测集合不一致必须拒绝。

## 测试验收

- repository 按 profile 聚合多个 run，支持模型过滤和稳定排序；
- 不同 profile 之间严格隔离；
- evaluation 按模型生成多个报告，空输入和混合数据校验；
- PlatformService 返回学生级报告且无记录报错；
- API endpoint 返回报告数组，未知 profile 返回 404；
- 现有 platform、evaluation、API 测试保持通过。

## 非目标

本阶段不自动配对 rule/BKT、不实现跨学生统计、不修改 observation schema、不改变线上测评和路径规划流程。
