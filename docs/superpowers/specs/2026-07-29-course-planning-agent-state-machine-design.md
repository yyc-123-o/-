# SkillForge 课程规划 Agent 状态机设计

- 日期：2026-07-29
- 状态：已确认，进入实施
- 范围：课程规划 Agent 自身的事件、状态、生命周期、内存会话和动态权重
- 非范围：其他 Agent、资源检索与生成、数据库、API、前端和大模型调用

## 1. 当前基线

课程规划模块已经具备确定性 `CoursePlanner`、章节后 `DepthUpdater`、`NodeWeightEngine`、两个 LangChain `StructuredTool` 和两个 LangGraph 兼容节点。当前缺失的是实际编译的 `StateGraph`、统一事件入口、会话生命周期、事件幂等、当前节点选择和 Agent 级结果合同。

## 2. 设计目标

1. 构建可以独立同步/异步调用的 `CoursePlanningAgent`。
2. 使用真实 LangGraph `StateGraph` 编排规划、更新、适配和节点选择。
3. 使用 `thread_id` 隔离学生会话，默认使用内存 Checkpointer。
4. 使用 `event_id` 防止同一事件被重复应用。
5. 首次规划、画像刷新和完成节点事件都保持路径不变量。
6. 将 `NodeWeightEngine` 接入 Agent，但动态权重不得修改主路径。
7. 返回结构化状态、当前节点、适配结果、审计记录和下一动作。

## 3. 架构原则

- LangGraph 只管理状态和路由，不重新计算教学规则。
- `CoursePlanner` 是首次路径的唯一事实源。
- `DepthUpdater` 是章节后路径变化的唯一事实源。
- `NodeWeightEngine` 是节点支持强度的唯一事实源。
- Agent 不调用网络、数据库、Neo4j、检索或大模型。
- 任何失败都不得覆盖最后一条有效路径。
- 同一 `thread_id + event_id` 重试不得重复完成节点或产生新路径 ID。

## 4. 依赖与文件边界

新增运行时依赖：

```text
langgraph>=0.6,<1
```

新增文件：

```text
src/skillforge_kb/agents/planning_agent_models.py
  事件、生命周期、下一动作、状态和结果合同

src/skillforge_kb/agents/planning_agent.py
  StateGraph 构造、节点、路由和 CoursePlanningAgent 入口

tests/unit/agents/test_planning_agent_models.py
tests/unit/agents/test_planning_agent.py
```

现有 `planning_tools.py` 保持工具适配职责，不继续扩张为完整状态机文件。

## 5. 事件合同

### 5.1 事件类型

```text
initialize
profile_refreshed
concepts_completed
reset
```

统一 `PlanningAgentEvent`：

```text
schema_version: planning-agent-event.v1
event_id: event_<sha256>
kind: PlanningEventKind
profile: LearnerProfileSnapshot | null
completed_concept_ids: tuple[str, ...]
```

校验规则：

- `initialize` 必须包含画像，不得包含完成节点。
- `profile_refreshed` 必须包含画像，完成节点必须为空。
- `concepts_completed` 至少包含一个唯一节点 ID；画像可选，缺省时使用会话内画像。
- `reset` 不得包含画像或完成节点。
- 完成节点 ID 重复时拒绝，不静默去重。

事件 ID 由调用方生成，代表不可变业务事件。相同事件 ID 携带不同内容属于调用方错误，Agent 返回结构化失败。

## 6. 生命周期与下一动作

`PlanningAgentStatus`：

```text
idle
planning
updating
ready
completed
failed
```

`PlanningNextAction`：

```text
start_current_node
wait_for_event
course_complete
reset_required
```

状态解释：

- `idle`：尚未初始化或已重置。
- `planning` / `updating`：图执行中的瞬态状态。
- `ready`：存在唯一当前 `AVAILABLE` 节点。
- `completed`：所有节点均为 `COMPLETED` 或 `SKIPPED`。
- `failed`：事件、版本或路径合同失败；保留最后有效路径。

## 7. LangGraph 状态

`CoursePlanningAgentState` 使用 `TypedDict(total=False)`：

```text
event: PlanningAgentEvent
profile: LearnerProfileSnapshot | null
path: PathDecision | null
adaptations: tuple[NodeAdaptationDecision, ...]
current_node_id: str | null
status: PlanningAgentStatus
next_action: PlanningNextAction
processed_events: tuple[ProcessedPlanningEvent, ...]
last_event_id: str | null
event_duplicate: bool
planning_audit: PlanningToolAudit | null
failure: PlanningAgentFailure | null
```

`ProcessedPlanningEvent` 保存 `event_id` 和规范化事件摘要。它既用于重复事件短路，也用于检测相同 ID 被用于不同载荷。

## 8. 状态图

```text
START
  |
  v
validate_and_route_event
  | initialize --------> create_path ----+
  | profile_refreshed -> update_path ----|---> recompute_adaptations
  | concepts_completed -> update_path ---+              |
  | reset -------------> reset_state                    v
  | duplicate ---------> preserve_state         select_current_node
  | invalid -----------> record_failure                  |
  +------------------------------------------------------+
                                                         v
                                                        END
```

路由规则：

- 只有 `idle` 会话可以接收新的 `initialize`。
- 未初始化会话不能接收刷新或完成事件。
- `completed` 会话允许 `reset`，其他业务事件返回失败。
- 重复且摘要一致的事件直接返回现有结果，`event_duplicate=true`。
- 相同事件 ID 但摘要不同返回失败，不修改路径。

## 9. 动态适配

首次规划或成功更新后，对所有未完成且未跳过节点调用 `NodeWeightEngine.evaluate()`：

- `COMPLETED` 和 `SKIPPED` 节点不生成新适配结果。
- `BLOCKED` 节点保留 `remediation` 语义。
- 适配顺序严格跟随路径顺序。
- 画像刷新可以改变未来节点的适配和深度，但不能改变路径 ID、节点集合或顺序。
- 已完成节点的历史路径字段保持不变。

## 10. 当前节点选择

完成适配后：

1. 若全部路径节点均为完成或跳过，状态为 `completed`，当前节点为空。
2. 否则必须存在且只存在一个 `AVAILABLE` 节点，状态为 `ready`。
3. 当前节点必须存在对应的 `NodeAdaptationDecision`。
4. 若课程未完成但没有可用节点，状态为 `failed`，错误码为 `no_available_node`。
5. 若出现多个可用节点，状态为 `failed`，错误码为 `multiple_available_nodes`。

## 11. 幂等与会话

- 默认 Checkpointer 为 LangGraph `InMemorySaver`。
- `thread_id` 必须是非空字符串，并进入 LangGraph `configurable` 配置。
- 每个线程维护独立画像、路径、适配和事件历史。
- 重复事件不重新运行规划或更新节点。
- `reset` 清空画像、路径、适配、当前节点、审计和失败，保留本次 reset 事件记录。
- 内存状态只用于当前阶段测试和单进程运行，不承诺进程重启恢复。

## 12. 失败合同

`PlanningAgentFailure`：

```text
code: invalid_event | invalid_transition | event_id_conflict |
      planning_error | adaptation_error | no_available_node |
      multiple_available_nodes
message: str
event_id: str
```

失败结果必须满足：

- `status=failed`。
- `next_action=reset_required`。
- 保留最后有效 `profile`、`path` 和 `adaptations`。
- 不把失败事件标记为成功处理；事件 ID 冲突除外，其已有成功记录保持不变。
- 未预期程序异常继续抛出，不伪装成业务失败。

## 13. Agent 公共接口

```python
agent = CoursePlanningAgent.create(
    catalog=catalog,
    attributes=attributes,
    planner_policy=planner_policy,
    node_weight_policy=node_weight_policy,
)

result = agent.invoke(event, thread_id="student-001")
result = await agent.ainvoke(event, thread_id="student-001")
snapshot = agent.get_state(thread_id="student-001")
```

`CoursePlanningAgentResult` 至少输出：

```text
thread_id
status
next_action
path
current_node
current_adaptation
adaptations
planning_audit
failure
last_event_id
event_duplicate
```

## 14. 测试策略

### 合同测试

- 四类事件字段约束。
- 重复完成节点拒绝。
- 事件摘要稳定并能检测内容冲突。
- 结果的当前节点和当前适配必须一致。

### 状态流测试

- 初始化产生路径、适配和当前节点。
- 完成当前节点后推进到下一个节点，路径 ID 不变。
- 仅画像刷新时路径顺序不变，只更新未来节点。
- 重复事件短路且结果稳定。
- 相同事件 ID 不同载荷失败。
- 未初始化更新失败且不产生路径。
- reset 清空会话并允许重新初始化。
- 同步和异步调用等价。
- 两个 `thread_id` 状态互不污染。
- 全部完成后进入 `completed`。

### 回归门禁

- 现有 217 项单元测试保持通过。
- Ruff 和 mypy 全部通过。
- 不需要 API Key、Docker 或外部服务。

## 15. 延后工作

- PostgreSQL/Redis Checkpointer。
- FastAPI 与前端。
- 资源简报、证据和生成 Agent 连接。
- 人工审核中断节点。
- 大模型自然语言解释。
- 分布式事件锁和跨进程幂等。
