# 平台侧 BKT 知识追踪设计

## 背景与目标

平台当前在 `src/skillforge_kb/assessment/update.py` 中使用固定加减分规则更新知识点掌握度。该规则可作为基线，但不能表达初始掌握、学习转移、猜测和粗心等因素。本次新增标准 Bayesian Knowledge Tracing（BKT）策略，供课程规划路径计算使用，同时保留规则策略，支持并行对比和逐步切换。

第一阶段只实现离散事件 BKT，不加入遗忘时间衰减、IRT 参数估计或跨知识点耦合。每个事件中的多个知识点独立更新，事件顺序由调用方保证。

## 方案选择

采用“独立 BKT 更新器 + 规则模型 fallback”：

- 直接替换规则更新器会改变现有路径结果，难以回滚和比较。
- 同时改造学情诊断 Agent 会产生两个掌握度来源，超出本阶段范围。
- 独立模块可以复用现有事件、账本和图谱校验，并允许后续通过配置灰度启用。

## 架构与接口

新增 `src/skillforge_kb/assessment/bkt.py`，不修改 `apply_assessment_event` 的默认行为。模块提供以下不可变 Pydantic 模型和纯函数：

### `BktParameters`

- `p_l0: float`：首次观测前的先验掌握概率，默认 `0.2`。
- `p_transition: float`：一次学习事件导致掌握的概率，默认 `0.1`。
- `p_guess: float`：未掌握时答对的猜测概率，默认 `0.2`。
- `p_slip: float`：已掌握时答错的粗心概率，默认 `0.1`。
- `model_version: str`：默认 `bkt.v1`。
- `parameter_version: str`：默认 `bkt-default.v1`。

所有概率限制在 `[0, 1]`。为避免退化模型，校验 `p_guess + p_slip < 1`，并要求版本非空。

### `BktState`

- `mastery_probability: float`：当前 `P(L)`，限制在 `[0, 1]`。
- `evidence_count: int`：已应用事件数，非负整数。
- `last_observed_at: datetime | None`：最近一次事件时间；有证据时必须为带时区时间。

该状态是计算结果的显式载体，不写入 `LearnerProfileSnapshot` 新字段，避免破坏现有画像协议。调用方可以从画像中的 `KnowledgeMastery.mastery_score` 和 `observed_at` 构造状态。

### `BktUpdateResult`

- `state_before: BktState`
- `state_after: BktState`
- `correct: bool`
- `model_version`、`parameter_version`
- `reason_codes: tuple[str, ...]`，至少包含 `bkt_update_applied`

### 纯函数

```python
def update_bkt_probability(
    prior_mastery: float,
    correct: bool,
    parameters: BktParameters,
) -> float

def apply_bkt_event(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
    event: AssessmentEvent,
    parameters: BktParameters | None = None,
) -> BktAssessmentUpdateResult
```

`apply_bkt_event` 返回与规则更新器兼容的账本和事实字段，并额外携带 BKT 元数据。推荐结果类型复用 `AssessmentUpdateResult` 的字段约束，再增加 `model_version`、`parameter_version` 和 `mastery_probability_before/after`；不改变 `AssessmentLedger` 的结构。

## BKT 更新公式

对当前掌握概率 `p = P(L)`：

1. 观测答对时：
   `P(L | correct) = p * (1 - p_slip) / (p * (1 - p_slip) + (1 - p) * p_guess)`。
2. 观测答错时：
   `P(L | incorrect) = p * p_slip / (p * p_slip + (1 - p) * (1 - p_guess))`。
3. 学习转移：
   `P(L_next) = posterior + (1 - posterior) * p_transition`。

首次没有画像掌握记录时使用 `p_l0`。每个事件中的概念独立计算，结果按 `event.concept_ids` 原始顺序写回。所有中间值和最终值都通过统一 clamp 限制到 `[0, 1]`；分母为零时抛出参数验证错误，而不是静默产生 NaN。

## 与现有账本和平台的关系

- 复用 `_validate_scope` 的语义：profile ID、图谱版本和概念 ID 必须匹配。
- 复用事件 ID 幂等规则：重复事件返回 `applied=False` 与 `duplicate_event`，账本对象保持不变。
- 继续追加 `event_id` 和 `evidence_refs` 到对应 `KnowledgeMastery.evidence_refs`。
- 正确事件不产生错误模式；错误事件沿用现有分类逻辑并更新 `error_patterns`。
- 默认 `apply_assessment_event` 继续使用规则策略；平台接入点后续通过显式 `model="bkt"` 选择 BKT，本阶段不隐式改变生产行为。

## 错误处理与确定性

- 参数、事件和账本入口均重新执行 Pydantic 校验，拒绝越界概率、重复概念、无时区时间和不一致图谱范围。
- 输入相同的参数、账本和事件必须产生完全相同的 JSON 可序列化结果。
- 未知概念、错误 profile 或 graph version 在任何状态更新前抛出 `ValueError`，原账本不变。
- 不对 hint、retry、response time 做额外数值惩罚；这些字段仅用于现有错误分类，避免把 BKT 观测模型与规则惩罚混合。

## 测试验收标准

新增 `tests/unit/assessment/test_bkt.py`，先写失败测试再实现，至少覆盖：

- 默认参数和边界参数校验；
- 首次答对、首次答错的公式结果；
- 连续答对单调上升、连续答错单调下降；
- `p_guess=0`、`p_slip=0` 等合法边界仍输出 `[0,1]`；
- 多概念事件保持输入顺序并保留无关掌握记录；
- 重复事件幂等；
- profile、graph version、未知概念校验失败且原账本不变；
- evidence_refs 和错误模式更新；
- 模型版本、参数版本、原因码稳定输出；
- 同一输入结果确定性，以及与规则基线可并列比较但不互相覆盖。

## 非目标与后续工作

本阶段不实现遗忘曲线、时间衰减、参数在线学习、IRT-BKT 融合、跨概念转移矩阵或前端模型选择器。待 BKT 单元测试和平台回归测试通过后，再评估把 `model="bkt"` 接入课程规划路径，并增加离线评估指标（Brier、LogLoss、AUC）与灰度开关。
