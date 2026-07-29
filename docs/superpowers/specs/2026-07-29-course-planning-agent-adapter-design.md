# SkillForge 课程规划 Agent 适配层设计

- 日期：2026-07-29
- 状态：已选定方案，进入实施
- 适用范围：LangChain Tool、LangGraph 兼容节点、幂等与失败审计
- 前置资产：`OntologyCatalog`、`LearnerProfileSnapshot`、`CoursePlanner`、`DepthUpdater`

## 1. 背景

课程图谱、画像适配、确定性路径规划、章节后更新和资源简报合同已经完成，但现有课程规划能力仍以普通 Python 对象暴露。后续多 Agent 编排需要真实的 LangChain Tool，以及能直接挂入 LangGraph `StateGraph` 的节点函数。

适配层必须保持框架与规划内核分离。LangChain/LangGraph 负责输入校验、调用、状态转换、重试标识和失败审计，不重新计算课程顺序、深度或硬先修关系。

## 2. 目标

1. 提供首次课程规划和章节后路径更新两个 `StructuredTool`。
2. 为相同语义输入生成稳定的请求摘要和结果摘要。
3. 提供可直接作为 LangGraph 节点调用的无框架状态转换函数。
4. 成功状态携带路径与审计记录；预期业务失败转换为结构化失败状态。
5. 保持 `PathDecision` 的路径 ID、节点集合、顺序和硬先修语义不变。

## 3. 非目标

- 不在本阶段构建完整 LangGraph 工作流或多 Agent 拓扑。
- 不调用大模型、向量检索、Neo4j、PostgreSQL 或网络服务。
- 不实现对话记忆、checkpoint 持久化、人工审核 UI 或重试队列。
- 不改变 `CoursePlanner`、`DepthUpdater`、`PlannerPolicy` 的计算规则。
- 不让 Agent 自行决定跳过节点、修改深度或解除硬先修阻塞。

## 4. 方案比较

### 方案 A：只暴露普通 Python 函数

依赖最少，但没有 LangChain 参数 schema、Tool 元数据和标准调用协议，后续仍需要二次包装。

### 方案 B：立即构建完整 LangGraph 工作流

可以一次性包含状态图、checkpoint 和人工节点，但会把尚未确定的编排与持久化设计提前固化，超出当前课程规划模块边界。

### 方案 C：StructuredTool + LangGraph 兼容节点

使用 `langchain_core.tools.StructuredTool` 提供真实工具接口；使用普通可调用节点消费和返回强类型状态片段。LangGraph 接受普通 callable 作为节点，因此此方案不需要提前增加 `langgraph` 运行时依赖。

采用方案 C。它满足当前框架接入目标，同时保留后续编排和 checkpoint 方案的选择空间。

## 5. 模块边界

新增 `src/skillforge_kb/agents/planning_tools.py`，只承担以下职责：

- 定义首次规划和路径更新的 Pydantic 输入模型。
- 定义工具审计、成功结果和节点失败模型。
- 构造 `create_course_plan` 与 `update_course_plan` 两个 `StructuredTool`。
- 构造首次规划节点和路径更新节点。
- 对语义输入和输出进行规范化摘要。

现有模块职责保持不变：

- `CoursePlanner`：唯一的首次路径决策实现。
- `DepthUpdater`：唯一的章节后路径更新实现。
- `PathDecision`：路径事实与稳定路径 ID。
- `OntologyCatalog`：课程结构和硬先修事实源。

## 6. 数据合同

### 6.1 首次规划输入

`CreateCoursePlanInput`：

```text
profile: LearnerProfileSnapshot
completed_concept_ids: tuple[str, ...] = ()
allow_skips: bool = true
```

`completed_concept_ids` 在摘要前去重校验并按字典序规范化。重复 ID 视为无效输入，避免调用方错误被静默掩盖。

### 6.2 路径更新输入

`UpdateCoursePlanInput`：

```text
existing: PathDecision
profile: LearnerProfileSnapshot
completed_concept_ids: tuple[str, ...]
```

更新输入至少包含一个本次完成节点。历史已完成节点继续由 `DepthUpdater` 从现有路径读取。

### 6.3 审计记录

`PlanningToolAudit`：

```text
schema_version: planning-tool-audit.v1
operation: create_course_plan | update_course_plan
request_digest: request_<sha256>
result_digest: result_<sha256>
path_id: path_<sha256>
profile_id: str
graph_version: str
policy_digest: policy_<sha256>
```

摘要使用排序键、ASCII JSON 和紧凑分隔符。审计记录不包含执行时间，使完全相同的重试得到相同结果。

### 6.4 工具结果

`PlanningToolResult`：

```text
schema_version: planning-tool-result.v1
path: PathDecision
audit: PlanningToolAudit
```

模型校验器重新计算 `result_digest`，拒绝路径或审计关键字段被篡改。

### 6.5 LangGraph 状态

`CoursePlanningState` 使用 `TypedDict(total=False)`，允许状态图逐步补齐字段：

```text
profile: LearnerProfileSnapshot
path: PathDecision
completed_concept_ids: tuple[str, ...]
allow_skips: bool
planning_status: planned | updated | failed
planning_audit: PlanningToolAudit
planning_failure: PlanningNodeFailure
```

节点只返回本次变化的状态片段，不复制整份状态。

## 7. 调用流程

首次规划：

```text
LangGraph state
  -> CreateCoursePlanInput 校验
  -> StructuredTool.invoke
  -> CoursePlanner.plan
  -> PlanningToolResult
  -> {path, planning_status=planned, planning_audit}
```

章节后更新：

```text
LangGraph state
  -> UpdateCoursePlanInput 校验
  -> StructuredTool.invoke
  -> DepthUpdater.update
  -> PlanningToolResult
  -> {path, planning_status=updated, planning_audit}
```

## 8. 错误处理

工具层保留原始验证行为：无效 Pydantic 输入抛出验证错误，图谱版本、未知节点或路径篡改抛出 `PlanningError`。

LangGraph 节点层只捕获可预期的 `PlanningError`、Pydantic `ValidationError` 和合同 `ValueError`，转换为：

```text
planning_status: failed
planning_failure:
  code: invalid_state | planning_error
  operation: create_course_plan | update_course_plan
  message: 稳定、非空的错误消息
```

更新节点失败时不返回新的 `path` 字段，因此 LangGraph 合并状态后会保留原路径。未预期异常不捕获，避免把程序错误伪装成业务失败。

## 9. 幂等与安全约束

1. 请求摘要覆盖工具名、完整标准画像、已完成节点、跳过开关和策略摘要。
2. 完成节点按字典序进入摘要，调用顺序不影响语义幂等键。
3. 结果摘要覆盖完整 `PathDecision` 和请求摘要。
4. 相同输入重试必须得到相同 `request_digest`、`result_digest` 和 `path_id`。
5. 策略、画像、图谱版本或完成节点发生变化时，请求摘要必须变化。
6. 工具和节点不能接受调用方覆盖路径 ID、策略摘要或节点顺序。

## 10. 测试要求

- `StructuredTool` 暴露稳定名称、描述和嵌套 Pydantic schema。
- 首次规划工具与直接调用 `CoursePlanner` 的结果完全一致。
- 路径更新工具与直接调用 `DepthUpdater` 的结果完全一致。
- 相同输入重复调用得到完全相同的工具结果。
- 完成节点输入顺序变化不改变请求摘要。
- 输入、策略或输出路径变化会改变相应摘要。
- 首次规划节点返回 `planned` 状态和审计记录。
- 更新节点返回 `updated` 状态并保持路径 ID 与节点顺序。
- 无效状态和规划错误返回结构化失败。
- 更新失败不覆盖已有路径。
- 全量单元测试、Ruff 和 mypy 保持通过。

## 11. 后续扩展

后续完整 Agent 编排可以直接把两个节点注册到 `StateGraph`，再增加画像诊断、资源简报、证据检索、资源生成和人工审核节点。checkpoint、持久化和重试策略由编排层决定，不改变本适配层的数据合同。
