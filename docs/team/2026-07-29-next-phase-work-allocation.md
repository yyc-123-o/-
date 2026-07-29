# SkillForge 下一阶段任务分工

## 1. 当前可信基线

- 课程图谱 `ai-course-v1` 已有 11 章、27 小节、140 概念、420 个三级深度节点和 147 条关系；硬先修无环、可达且顺序已校验。
- 图谱发布器可幂等发布课程结构到 Neo4j，但正式图谱尚未发布证据、来源或资源边。
- 知识库融合和来源治理已完成候选层处理；当前候选覆盖 12/140 个概念，仍有 128 个覆盖缺口和 15 个未知 ID。
- `LearnerProfileSnapshot` 已定义掌握度、四维能力、错误模式和学习偏好，但 `ProfileAdapter` 当前只适配掌握度，且历史 ID 映射为空。
- 确定性课程规划内核已实现稳定排序、跳过、阻塞、三级深度和章节后更新；路径集合与顺序不可变。

## 2. 关键架构原则

1. 课程图谱是结构事实源，画像是诊断事实源，规划策略是版本化规则源。
2. 主路径只由硬先修和课程教学顺序决定；动态节点权重不得重排、删除或新增路径节点。
3. 节点动态权重用于资源强度、练习配额、预计学习时长和教学重点，不替代 `delivery_depth` 的确定性规则。
4. `PathDecision` 只描述路径，资源生成只能消费经过校验的 `ResourceBrief`，不能自行改写路径、深度或先修关系。
5. 任何生成性结论都必须绑定已审核的证据片段；候选 JSONL 不能直接进入 Neo4j、检索结果或生成提示。

## 3. 动态节点权重原则

定义独立的、冻结的 `NodeWeightPolicy`。每个未完成节点输出 `NodeAdaptation`，包含 `attention_weight`、`resource_mode`、`effort_multiplier`、`assessment_emphasis` 和稳定原因码。

### 3.1 输入

- 图谱：概念难度、核心章节标记、三级学习产出、先修关系和资源蓝图标签。
- 画像：概念掌握度及置信度、四维能力及置信度、错误模式、学习目标和偏好。
- 路径：当前节点的确定性 `delivery_depth`、状态和硬先修阻塞项。

### 3.2 计算

所有子分数都限制在 `[0, 1]`：

```text
knowledge_gap = 1 - effective_mastery
uncertainty = 1 - evidence_confidence
structural_need = 0.5 * normalized_difficulty + 0.5 * chapter_core
error_risk = relevant_error_pattern_ratio
ability_gap = concept_required_ability_gap
goal_relevance = concept_goal_tag_match

attention_weight = clip(
    0.30 * knowledge_gap
  + 0.15 * uncertainty
  + 0.15 * structural_need
  + 0.20 * error_risk
  + 0.10 * ability_gap
  + 0.10 * goal_relevance,
  0,
  1,
)
```

- 未测数据使用保守值：`knowledge_gap=1`、`uncertainty=1`，但不虚构能力或目标相关度。
- 硬先修阻塞时，`delivery_depth` 保持 `intro`，`resource_mode=remediation`，可提高补救资源关注度，但绝不能请求进阶或专业资源。
- 学习偏好仅影响资源形式和节奏，例如代码语言、图示、分步讲解、每周时长；不得提高掌握度、解除阻塞或提升深度。
- 策略版本、输入快照版本和输出原因码必须进入审计记录；规则变化产生新策略摘要。

## 4. 规划与资源的中间契约

新增 `ResourceBrief`，由课程规划侧的 `ResourceBriefBuilder` 构造：

```text
ResourceBrief
  request_version, path_id, graph_version, profile_id, policy_digest
  concept_id, chapter_id, section_id, sequence, delivery_depth
  learning_outcomes, assessment_kinds, hard_prerequisites
  node_adaptation, error_pattern_hints, presentation_preferences
  required_resource_types, evidence_filters, citation_requirements
```

资源生成 Agent 只接收 `ResourceBrief + EvidenceBundle`，输出讲义、实操指南和测试题；每条关键结论必须带 `source_id + chunk_id + locator`。资源 Agent 不能改写路径顺序、教学深度、节点权重或图谱版本。

## 5. 分工与交付物

| 优先级 | 任务包 | 建议负责人 | 交付物 | 完成验收 |
| --- | --- | --- | --- | --- |
| P0 | 证据图谱与审核门禁 | 知识库/图谱同学 A | `EvidenceSource`、`EvidenceChunk`、`ConceptEvidenceLink` 契约和审核状态机 | 未审核候选不能被发布；每条已发布证据可追溯许可证、定位符和哈希 |
| P0 | 画像映射与完整适配 | 学情画像同学 + 知识库同学 B | 审核过的旧 ID 一对一映射；适配 abilities、error_patterns、preferences | 示例画像可转为版本一致快照；未知、复合、重复和版本错误被拒绝 |
| P0 | 资源蓝图覆盖 | 知识库/图谱同学 B | `resource_blueprints_v1.yaml`，覆盖章节、小节和 140 x 3 深度节点 | 每个 `ConceptLevel` 都能生成含学习产出、资源类型和评测要求的骨架 |
| P0 | 动态节点权重策略 | 课程规划 Agent（我方主责）+ 算法同学 | `NodeWeightPolicy`、`NodeAdaptation`、三类画像测试 | 权重可复算、有界、单调；不重排路径；阻塞节点不得升级深度 |
| P0 | 路径到资源桥接 | 课程规划 Agent（我方主责）+ 资源生成 Agent 同学 | `ResourceBrief`、`ResourceBriefBuilder`、契约测试 | 相同输入简报完全一致；简报只含下游所需的最小画像字段 |
| P1 | 混合检索与证据包 | 领域检索 Agent 同学 | `EvidenceBundle`，支持 concept/depth/language/type/review 筛选 | 返回仅含已审核证据；每项有来源定位；无证据时明确失败而非编造 |
| P1 | 三类资源生成与校验 | 资源生成 Agent 同学 | 讲义、实操、测试题 schema；深度模板；引用和代码校验器 | 资源严格符合 `ResourceBrief`；关键结论和题目均具证据绑定 |
| P1 | Agent 适配层 | 智能体搭建同学 | LangChain Tool 或 LangGraph 节点包装，状态契约与幂等调用 | 规划内核不依赖框架；重试不生成不同路径；状态可审计 |
| P1 | 章节后反馈闭环 | 学情诊断/交互导学同学 | 答题结果到新画像快照的更新契约 | 只更新未完成节点的资源策略；已完成章节与路径顺序不变 |
| P2 | 图谱查询和版本隔离 | 知识库/图谱同学 A | 结构化先修查询、图谱版本过滤和旧版本隔离测试 | hard/soft、`min_mastery`、review/version 不丢失；跨版本查询不混淆 |
| P2 | 评测与演示数据 | 算法同学 + 前端同学 | 零基础/中等/进阶三套全链路样例和 60 组测试 | 覆盖率、难度适配率、证据绑定率和幻觉率均可复现 |

## 6. 依赖顺序

```text
证据审核门禁 + 画像完整适配 + 资源蓝图
                  |             |
                  v             v
         NodeWeightPolicy -> ResourceBriefBuilder
                                      |
                                      v
                         EvidenceBundle + 资源生成
                                      |
                                      v
                          Agent 编排、审核与反馈闭环
```

P0 是当前实施门槛。没有审核证据、完整画像适配和资源蓝图时，资源生成 Agent 只能产生不可审计的演示文本，不能作为正式闭环。

## 7. 仍待完成的项目部分

1. 正式证据边和每概念、每深度的资源覆盖。
2. 历史画像 ID 映射、能力/错误模式/偏好适配和置信度校准。
3. 动态节点权重、资源强度和 `ResourceBrief` 的版本化契约。
4. BM25、向量检索、图谱遍历融合为可审计 `EvidenceBundle`。
5. 三类资源的结构化生成、证据引用、代码运行与试题质量校验。
6. 课程规划、检索、生成、审核、裁判和导学的编排状态与持久化。
7. PostgreSQL 的画像、路径、资源和审计日志存储；FastAPI 接口和前端路径/资源展示。
8. 3 类画像、60 组测试、幻觉率、难度适配率、覆盖率和用户演示的评测基线。
