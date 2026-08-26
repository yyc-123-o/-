# BKT 平台测评接入设计

## 目标

让 BKT 真正参与平台学习闭环：学生提交测评后，平台根据本次运行请求选择规则模型或 BKT 更新画像，再触发课程规划重新计算路径。默认行为保持规则模型，已有请求和接口无需修改即可继续运行。

## API 变更

在 `src/skillforge_kb/platform/models.py` 新增：

```python
class AssessmentModel(StrEnum):
    RULE = "rule"
    BKT = "bkt"
```

`PlatformRunRequest` 新增字段：

```python
assessment_model: AssessmentModel = AssessmentModel.RULE
```

字段采用 `extra="forbid"` 的既有策略；旧 JSON 缺失字段时自动取 `rule`。`build_request_digest` 使用完整模型序列化，因此同一幂等键在不同测评模型下生成不同请求摘要；`build_run_id` 保持只使用 profile 与幂等键，避免破坏现有幂等存储协议。

## 测评更新流程

`PlatformService.submit_assessment` 根据 `request.assessment_model` 分派：

- `RULE`：调用现有 `apply_assessment_event`，结果类型和行为完全不变。
- `BKT`：调用 `apply_bkt_event`，使用默认 `BktParameters`，读取同一个 `AssessmentLedger(profile=request.profile)`。

两个更新器都返回带新画像的 ledger。平台只依赖共同字段 `ledger.profile`，随后执行现有 `PROFILE_REFRESHED` 规划事件；通过测评的提交继续执行 `CONCEPTS_COMPLETED`，失败提交保持当前节点开放。

BKT 结果中的 `model_version` 和 `parameter_version` 不直接写入画像协议。平台步骤的输出摘要继续记录更新后画像，模型选择通过请求摘要和运行请求持久化，满足审计要求且不修改画像 JSON schema。

## 幂等与错误语义

- `assessment_id` 的 repository 幂等检查保持不变；相同 payload 重放返回同一 `PlatformRunResult`。
- 事件 ID 冲突或 payload 不同仍按现有逻辑拒绝。
- BKT 的 scope 校验、重复事件校验和规则模型一致。
- 不支持的模型值由 Pydantic 在请求校验阶段拒绝。
- 不新增自动 fallback：选择 BKT 时若参数或账本校验失败，平台返回现有失败状态，避免静默切换模型。

## 规划影响

课程规划器无需修改。BKT 更新得到的 `KnowledgeMastery.mastery_score` 会被现有 `_mastery_index`、前置条件判断、跳过阈值和交付深度计算直接消费。这样可以验证：答题结果改变掌握概率，重新规划后节点状态或深度发生可解释变化。

## 测试设计

新增或扩展 `tests/unit/platform/test_models.py`：

- 缺省 `assessment_model` 为 `rule`；
- `bkt` 能通过模型校验并进入请求摘要；
- 非法模型值被拒绝；
- rule/bkt 对相同请求生成不同 request digest，run id 规则保持兼容。

扩展 `tests/unit/integration/test_three_agent_platform_flow.py` 或新增平台测评测试：

- BKT 请求提交正确答案后，画像掌握度等于标准 BKT 结果，并触发重新规划；
- BKT 请求提交错误答案后，错误模式被记录且当前节点不完成；
- BKT 测评重复提交保持幂等；
- rule 请求结果继续保持现有 `0.56` 等基线数值。

## 非目标

本阶段不修改前端控件、不实现遗忘模型、不持久化 BKT 参数到画像、不改变默认 rule 行为，也不引入新的跨 Agent 协议字段。
