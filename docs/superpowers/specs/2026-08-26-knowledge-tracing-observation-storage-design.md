# 知识追踪预测快照存储设计

## 目标

在平台真实测评流程中记录答题前的掌握概率，使 rule/BKT 结果可以被离线评估器消费。快照与测评 ID 绑定，遵循现有 repository 幂等和线程安全语义，不扩大 `PlatformRunResult` 或画像 JSON 协议。

## 数据模型

复用 `skillforge_kb.evaluation.knowledge_tracing.KnowledgeTracingObservation`：

- `observation_id` 使用 `assessment_id`，保证一次测评只有一个预测快照。
- `profile_id`、`concept_id` 来自平台请求和测评提交。
- `model_version`：rule 使用 `rule.v1`，BKT 使用 `bkt.v1`。
- `predicted_mastery`：答题前画像中该概念的 `mastery_score`；没有记录时 rule 使用 `0.50`，BKT 使用 `BktParameters.p_l0`（默认 `0.20`）。
- `correct`：提交评分是否达到 `passing_score`。
- `observed_at`：平台创建 `AssessmentEvent` 时的 UTC 时间。

## Repository 接口

扩展 `PlatformRunRepository` Protocol 和 `InMemoryPlatformRunRepository`：

```python
def get_prediction_observation(
    self, run_id: str, assessment_id: str
) -> KnowledgeTracingObservation | None

def save_prediction_observation(
    self, run_id: str, assessment_id: str,
    observation: KnowledgeTracingObservation
) -> None

def list_prediction_observations(
    self, run_id: str
) -> tuple[KnowledgeTracingObservation, ...]
```

存储键为 `(run_id, assessment_id)`。保存时要求 observation ID 等于 assessment ID、profile 与 run request 一致、概念和模型字段合法；已有相同 observation 时必须内容相等，否则抛出冲突错误。

## 平台流程

`PlatformService.submit_assessment` 在 repository 的已有 `get_assessment` 幂等检查之后：

1. 创建 `AssessmentEvent` 前，从 `request.profile.knowledge_mastery` 查找当前概念分数；缺失时使用当前模型先验。
2. 创建带 UTC 时间戳的事件，同时构造 `KnowledgeTracingObservation`，`correct` 使用最终评分结果。
3. 调用 rule/BKT 更新器并完成现有重新规划流程。
4. 仅当测评结果成功保存时调用 `save_prediction_observation`；重复提交在步骤 0 返回，不重复写入。

如果更新器抛出异常或平台运行失败，不写 observation，避免评估数据包含未完成事件。通过和失败测评都记录，只要画像更新流程成功；失败测评用于衡量模型对错误答案的概率校准。

## 评估导出

本阶段只提供 repository 的读取接口，不自动生成报告。调用方可以：

```python
observations = repository.list_prediction_observations(run_id)
report = evaluate_knowledge_tracing(observations)
```

跨运行汇总由上层服务完成，避免把存储层与报告格式耦合。

## 测试验收

- repository 保存、读取、列表顺序和冲突校验；
- rule 首次测评记录预测 `0.50`，BKT 首次测评记录预测 `0.20`；
- 已有 mastery 时记录该分数；
- 正确和错误测评都写 observation；
- 重复 assessment 返回相同结果且 observation 数量不增加；
- 更新失败不产生 observation；
- 现有 platform、assessment、evaluation 测试保持通过。

## 非目标

本阶段不持久化 BKT 参数、不修改画像 schema、不自动聚合跨学生报告、不实现数据库 adapter；后续可在同一 Protocol 上增加 PostgreSQL 实现。
