# SkillForge 课程规划内核设计

- 日期：2026-07-28
- 状态：已实现
- 适用范围：课程规划 Agent 的确定性路径与深度决策内核
- 前置资产：`ai-course-v1` 课程知识图谱与 `LearnerProfileSnapshot`

## 1. 目标

本阶段实现课程规划 Agent 的纯算法内核，将版本一致的学习者画像与课程知识图谱转换为完整、稳定、可解释的 `PathDecision`。规划结果必须覆盖全部必修概念，保留已掌握节点供审计，并为每个未跳过节点确定教学深度。

内核不调用大模型、不连接 Neo4j、不写数据库，也不负责资源生成或多智能体编排。LangChain Tool、LangGraph 节点、API 和持久化将在内核稳定后通过适配层接入，不参与排序和深度计算。

## 2. 已确认产品约束

1. 默认生成完整必修课程，不采用目标概念子路径。
2. 路径概念集合与顺序一次性生成，学习过程中保持不变。
3. 已掌握概念不从路径删除，标记为 `skipped`。
4. 每章完成后的新画像只允许更新未完成节点的阻塞状态与教学深度。
5. 三级深度由版本化规则表决定，不由大模型评分。
6. 画像数据缺失或低置信度时保守降级，不伪造中等能力。
7. 硬先修未测或未达到门槛时，后继概念不能选择 `intermediate` 或 `advanced`。
8. 相同输入必须产生字节级等价的规范结果。

## 3. 架构选择

采用确定性规划内核：

```text
OntologyCatalog -----------+
                           |
LearnerProfileSnapshot ----+--> CoursePlanner --> PathDecision
                           |
PlannerPolicy -------------+
                                      |
                                      +--> 后续 LangChain/LangGraph 适配层
```

不采用以下方案：

- Neo4j 查询驱动：会把核心算法绑定在线服务，增加版本一致性和测试成本。
- LangGraph 流程优先：会把一个可验证的确定性算法拆散到多个编排节点。
- 模型打分：当前样本和评测不足以支持不可解释的路径决策。

`OntologyCatalog` 是课程结构事实来源；`LearnerProfileSnapshot` 是诊断事实输入；`PlannerPolicy` 是阈值与权重事实来源；`PathDecision` 是不可变的规划决策快照。

## 4. 模块边界

新增 `src/skillforge_kb/planning/`：

```text
planning/
  models.py      AbilityWeights、PlannerPolicy、PathNode、PathDecision 和枚举
  ordering.py    必修概念的稳定拓扑排序与位置索引
  planner.py     首次路径生成、状态/深度决策和解释原因
  updater.py     保持路径不变的章节后更新
  serialization.py  规范 JSON 与确定性 path_id
```

职责约束：

- `models.py` 只定义并校验数据契约。
- `ordering.py` 只读取图谱结构，不读取学习者画像。
- `planner.py` 不修改输入对象，不执行 I/O。
- `updater.py` 不允许新增、删除或重排节点。
- `serialization.py` 不包含课程策略。

## 5. 数据契约

### 5.1 PlannerPolicy

默认策略版本为 `planner-policy.v1`：

| 字段 | 默认值 | 作用 |
| --- | ---: | --- |
| `version` | `planner-policy.v1` | 决策追溯 |
| `minimum_confidence` | `0.60` | 掌握度作为有效证据的最低置信度 |
| `skip_mastery` | `0.85` | 跳过概念的掌握度门槛 |
| `skip_confidence` | `0.80` | 跳过概念的置信度门槛 |
| `mastery_weight` | `0.60` | 综合准备度中的概念掌握度权重 |
| `ability_weight` | `0.40` | 综合准备度中的能力权重 |
| `intermediate_threshold` | `0.65` | 进阶层最低准备度 |
| `advanced_threshold` | `0.85` | 专业层最低准备度 |

能力权重由冻结的 `AbilityWeights` 值对象承载，固定为：

- `theoretical_understanding`: `0.30`
- `coding_ability`: `0.25`
- `mathematical_foundation`: `0.25`
- `problem_solving`: `0.20`

模型校验必须保证能力权重和为 1、掌握度与能力权重和为 1、`intermediate_threshold < advanced_threshold`，且所有阈值位于 `[0, 1]`。策略及嵌套能力权重均不可原地修改。

### 5.2 PathNode

每个必修概念对应一个节点：

```text
concept_id
chapter_id
section_id
sequence
status: skipped | available | blocked | pending | completed
delivery_depth: intro | intermediate | advanced | null
hard_prerequisite_ids[]
blocking_prerequisite_ids[]
reason_codes[]
```

状态语义：

- `skipped`：概念掌握度和置信度同时达到跳过门槛；`delivery_depth=null`。
- `available`：硬先修满足且当前可以学习。
- `blocked`：至少一个硬先修未测、低置信度或低于关系门槛。
- `pending`：硬先修满足，但稳定序列中存在更早的未完成、未跳过节点。
- `completed`：仅在章节后更新时由调用方明确提供的完成概念集合产生。

原因使用稳定代码而不是自然语言，例如：`mastery_skip_threshold_met`、`mastery_missing`、`ability_incomplete`、`hard_prerequisite_unassessed`、`hard_prerequisite_below_threshold`、`ready_for_intermediate`。展示层后续将原因码本地化。

### 5.3 PathDecision

```text
schema_version: path-decision.v1
path_id
profile_id
graph_version
policy_version
policy_digest
generated_at
nodes[]
```

`policy_digest` 是完整策略规则规范 JSON 的 SHA-256；相同版本字符串但不同阈值或权重必须产生不同摘要并禁止更新既有路径。`path_id` 是确定性内容 ID，由 `profile_id`、`graph_version`、`policy_version`、`policy_digest` 和有序 `concept_id` 列表的规范 JSON 计算 SHA-256。`generated_at` 不参与 `path_id`。重复规划的语义字段必须完全一致；测试比较时排除调用方提供的时间戳。

`PathNode` 和 `PathDecision` 使用冻结的 Pydantic 模型；节点集合、先修集合、阻塞集合和原因码集合均使用不可变元组。更新结果可以安全复用冻结对象，但任何调用方都不能原地修改既有规划快照。

## 6. 稳定路径算法

### 6.1 候选集合

只选择 `Concept.required=true` 的概念。每个候选概念必须有唯一 `TeachingAssignment` 和可解析的章节、小节位置。规划前必须执行完整图谱校验。

### 6.2 排序

只使用 `hard_prerequisite` 边构造排序 DAG。Kahn 拓扑排序的就绪队列使用以下稳定键：

```text
(chapter.order, section.order, teaching_assignment.order, concept.id)
```

如果一个必修概念依赖非必修硬先修，该先修仍用于阻塞判断，但不进入完整必修路径。图谱校验应保证正式课程中此类边已被明确审核。

排序必须满足：

- 任一必修硬先修位于其后继之前；
- 无依赖顺序时遵循课程教学位置；
- 相同图谱重复排序结果一致。

## 7. 掌握度与硬先修判断

画像中的 `knowledge_mastery` 按 `concept_id` 建立唯一索引。重复概念、未知概念或图谱版本不一致时拒绝规划。

有效掌握度必须同时满足：

- `assessment_status=assessed`；
- `mastery_score` 非空；
- `confidence >= minimum_confidence`。

硬先修逐边检查其 `min_mastery`：

- 不存在画像记录或 `not_assessed`：阻塞，原因 `hard_prerequisite_unassessed`。
- 置信度不足：阻塞，原因 `hard_prerequisite_low_confidence`。
- 掌握度低于关系门槛：阻塞，原因 `hard_prerequisite_below_threshold`。
- 达到门槛或该先修节点已被明确完成：满足。

`skipped` 仅表示该概念不需要再次学习，不会删除它，也不会绕过对后继的门槛检查。

## 8. 教学深度规则

### 8.1 能力分

能力分使用四维画像加权平均。每个维度必须存在，且其 `confidence >= minimum_confidence`；否则能力数据不完整。

### 8.2 准备度

当概念有效掌握度和完整能力分都存在时：

```text
readiness = mastery_score * 0.60 + ability_score * 0.40
```

深度选择：

- `readiness < 0.65`：`intro`
- `0.65 <= readiness < 0.85`：`intermediate`
- `readiness >= 0.85`：`advanced`

以下任一情况强制最多为 `intro`：

- 概念未测；
- 概念置信度低于 `minimum_confidence`；
- 四维能力缺少任一项；
- 任一能力置信度不足；
- 存在硬先修阻塞。

`skipped` 节点深度为 `null`。该规则有意保守：未知状态不能被当成中等能力。

## 9. 初始状态计算

先计算所有节点的 `skipped`、阻塞项和深度，再按稳定序列决定可执行状态：

1. `skipped` 节点保持 `skipped`。
2. 有硬先修阻塞的节点为 `blocked`。
3. 第一个既未跳过又未阻塞的节点为 `available`。
4. 其余无阻塞节点为 `pending`。

这使路径图能够同时表达课程全貌和当前唯一的推荐入口。

## 10. 章节后更新

`DepthUpdater.update(existing, profile, completed_concept_ids)` 执行以下校验：

- `profile_id` 与既有决策一致；
- `graph_version` 一致；
- 策略版本一致；
- 完成概念都存在于既有路径；
- 既有路径的概念集合、顺序和位置仍与当前图谱相符。

更新规则：

1. 保持 `path_id`、节点数、节点顺序、章节和小节位置不变。
2. 初始 `skipped` 节点保持不变。
3. 已完成节点变为 `completed`，保留其既有 `delivery_depth`。
4. 仅对未完成节点重算硬先修、状态、深度和原因码。
5. 已完成概念可满足对应后继的硬先修，不要求新画像重复携带其掌握度。
6. 不允许新增、删除、替换或重排主路径节点。

## 11. 错误处理

定义 `PlanningError`，至少覆盖：

- 图谱校验失败；
- 画像与图谱版本不一致；
- 画像含重复或未知概念；
- 策略阈值或权重非法；
- 更新画像、策略或身份与既有决策不一致；
- 完成概念不在路径中；
- 既有路径被篡改或已不匹配图谱。

能力缺失、概念未测、低置信度和硬先修暂未满足不是异常，而是保守降级或阻塞状态。

## 12. 测试与验收

### 12.1 契约测试

- 默认策略通过，非法权重和阈值被拒绝。
- `skipped` 节点只能使用 `delivery_depth=null`。
- `available`、`blocked`、`pending` 节点必须有教学深度。
- 路径节点序列必须连续且概念唯一。

### 12.2 排序测试

- 140 个概念中的全部必修概念覆盖率为 100%。
- 所有必修硬先修顺序违反数为 0。
- 无依赖节点按章节、小节和教学顺序稳定排列。
- 相同图谱重复运行得到相同序列。

### 12.3 画像类型测试

- 零基础画像：完整路径，未测概念为 `intro`。
- 有一定基础画像：高掌握节点保留为 `skipped`，其他节点按规则选择深度。
- 进阶画像：满足全部证据和先修条件时可选择 `advanced`。
- 缺失能力或低置信度：最多 `intro`。
- CNN 或其他目标的硬先修不足：目标不能进入 `intermediate/advanced`。

### 12.4 更新不变式测试

- 更新前后 `path_id`、概念集合和顺序一致。
- 已完成节点深度保持不变。
- 只更新未完成节点。
- 身份、图谱版本或策略版本不一致时失败。

### 12.5 质量门槛

```powershell
uv run pytest tests/unit/planning -q
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
```

规划内核单元测试不得依赖 Docker、Neo4j、网络或大模型。

## 13. 本阶段不实现

- LangChain Tool 与 LangGraph 工作流节点；
- 路径持久化和 FastAPI；
- 学情诊断与掌握度更新算法；
- 资源检索、讲义、实操指南和测试题生成；
- 多 Agent 辩论、裁判和降维重生成；
- 前端路径图。

这些能力只能消费版本化 `PathDecision`，不能绕过或重写规划内核的确定性结果。
