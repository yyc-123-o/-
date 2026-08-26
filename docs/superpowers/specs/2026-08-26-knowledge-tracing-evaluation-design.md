# 知识追踪离线评估设计

## 目标

为 rule 与 BKT 知识追踪策略建立统一、可复现的离线评估接口，量化概率预测质量，再决定是否引入遗忘或参数自适应。评估模块只消费已生成的预测概率和二值答题结果，不修改线上测评流程。

## 输入模型

新增 `src/skillforge_kb/evaluation/knowledge_tracing.py`，定义冻结模型 `KnowledgeTracingObservation`：

- `observation_id: str`：唯一观测 ID。
- `profile_id: str`：学生画像 ID。
- `concept_id: str`：知识点 ID。
- `model_version: str`：如 `rule.v1` 或 `bkt.v1`。
- `predicted_mastery: float`：答题前预测掌握概率，范围 `[0,1]`。
- `correct: bool`：实际答题结果。
- `observed_at: datetime`：带时区时间。

评估函数签名：

```python
def evaluate_knowledge_tracing(
    observations: Sequence[KnowledgeTracingObservation],
    *,
    model_version: str | None = None,
    data_version: str = "knowledge-tracing-eval.v1",
) -> KnowledgeTracingEvaluationReport
```

输入至少包含一条观测；观测 ID 不得重复；指定 `model_version` 时所有观测必须一致；不指定时从首条观测推断并要求全体一致。

## 指标模型

`KnowledgeTracingMetrics` 包含：

- `sample_count`：观测数量。
- `positive_count`、`negative_count`：正确与错误数量。
- `brier_score`：`mean((p - y)^2)`，越低越好。
- `log_loss`：`-mean(y*log(p)+(1-y)*log(1-p))`，概率先 clamp 到 `[1e-15, 1-1e-15]`。
- `auc`：按预测概率排序计算 ROC-AUC；若样本只有一个类别则为 `None`，不能伪造 0.5。

新增 `KnowledgeTracingEvaluationReport`：

- `schema_version="knowledge-tracing-evaluation.v1"`。
- `data_kind="observed_predictions"`。
- `data_version`、`model_version`。
- `observations`：按输入顺序保存的观测元数据。
- `metrics`：上述指标。
- `disclaimer`：固定声明“离线预测指标不等于真实学习效果”。
- `report_digest`：对去除 digest 的 JSON 内容计算 SHA-256。

## 模型比较

提供 `compare_knowledge_tracing_reports(reports)`，要求报告数据版本和观测 ID 集合一致，返回冻结的 `KnowledgeTracingComparison`，其中包含按 `brier_score`、`log_loss` 升序（越低越优）排序的模型版本、各指标差值和基准模型。AUC 缺失时只作为不可比较字段，不参与排序。

第一阶段不直接从 `AssessmentEvent` 重放 BKT 或规则模型，避免把预测时刻（答题前/答题后）混淆。调用方负责在提交事件前记录预测概率，评估器只做确定性统计。

## 错误处理与数值稳定性

- 概率越界、无时区时间、重复观测 ID、空输入和模型版本不一致均抛出 `ValueError`/`ValidationError`。
- `NaN` 和无穷值必须被拒绝；所有输出指标限制在合法范围。
- AUC 使用并列概率的平均秩；正负样本不足时返回 `None`。
- 相同输入必须生成相同 digest 和指标，JSON 序列化可往返。

## 测试验收标准

新增 `tests/unit/evaluation/test_knowledge_tracing.py`，覆盖：

- Brier 和 LogLoss 的已知小样本结果；
- 完美预测 AUC=1、反向预测 AUC=0、单类别 AUC=None；
- 并列概率的 AUC 平均秩；
- 概率边界 clamp 后 LogLoss 有限；
- 空输入、重复 ID、模型版本不一致和无时区时间失败；
- 报告 digest 往返和篡改检测；
- rule 与 BKT 报告比较排序及数据集不一致拒绝。

## 非目标

本阶段不生成预测序列、不修改 `AssessmentLedger`、不接入前端、不实现参数搜索、遗忘曲线或显著性检验。
