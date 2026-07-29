# SkillForge 下一阶段任务分工

## 1. 当前可信基线

- 课程图谱 `ai-course-v1` 已有 11 章、27 小节、140 概念、420 个三级深度节点和 147 条关系；硬先修无环、可达且顺序已校验。
- 图谱发布器可幂等发布课程结构到 Neo4j；证据审核清单、发布状态与只读查询契约已实现，但生产清单仍为 0 条已发布证据，尚未发布证据、来源或资源边。
- 知识库融合和来源治理已完成候选层处理；当前候选覆盖 12/140 个概念，仍有 128 个覆盖缺口和 15 个未知 ID。
- `ProfileAdapter` 已完整适配掌握度、四维能力、错误模式、学习偏好、测评批次和证据引用；生产历史 ID 映射仍为空，必须等待人工审核的一对一映射，不能伪造 reviewer。
- 140 个概念的能力需求和 420 个三级资源蓝图已形成强类型、不可变目录；CNN、RAG 等核心章节具有区分性需求。
- 确定性课程规划内核已实现稳定排序、跳过、阻塞、三级深度和章节后更新；`NodeWeightEngine` 已实现可复算贡献项、保守置信度下限和完成节点拒绝，路径集合与顺序不可变。
- `ResourceBrief`、`EvidenceBundle`、四类资源输出和框架中立校验器已实现；真实 LangChain/LangGraph 包装和大模型生成尚未开始。

## 2. 关键架构原则

1. 课程图谱是结构事实源，画像是诊断事实源，规划策略是版本化规则源。
2. 主路径只由硬先修和课程教学顺序决定；动态节点权重不得重排、删除或新增路径节点。
3. 节点动态权重用于资源强度、练习配额、预计学习时长和教学重点，不替代 `delivery_depth` 的确定性规则。
4. `PathDecision` 只描述路径，资源生成只能消费经过校验的 `ResourceBrief`，不能自行改写路径、深度或先修关系。
5. 任何生成性结论都必须绑定已审核的证据片段；候选 JSONL 不能直接进入 Neo4j、检索结果或生成提示。

## 3. 动态节点权重原则

定义独立的、冻结的 `NodeWeightPolicy`。每个未完成节点输出 `NodeAdaptationDecision`，包含 `readiness_score`、`support_need_score`、`support_intensity`、`effort_multiplier`、`assessment_emphasis`、贡献项和稳定原因码。`resource_mode` 仅是 `support_intensity` 的只读兼容名称，不存在第二套可分叉状态。

### 3.1 输入

- 图谱：概念难度、核心章节标记、三级学习产出、先修关系和资源蓝图标签。
- 画像：概念掌握度及置信度、四维能力及置信度、错误模式、学习目标和偏好。
- 路径：当前节点的确定性 `delivery_depth`、状态和硬先修阻塞项。

### 3.2 计算

所有子分数都限制在 `[0, 1]`：

```text
ability_fit = sum(learner_ability[d] * concept_ability_demand[d])
readiness = 0.60 * effective_mastery + 0.40 * ability_fit
ability_gap = max(0, concept_difficulty_prior - ability_fit)
support_need = 0.55 * mastery_gap + 0.25 * error_risk + 0.20 * ability_gap
```

- 未测或低置信度掌握度/能力不虚构高分，`support_need >= 0.60` 且支持强度至少为 `scaffolded`；完全未测掌握度使用保守上限。
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

当前代码层 P0 契约已完成；实际业务闭环仍被“人工审核画像 ID 映射”和“生产已发布证据为 0”两项数据门禁阻塞。测试中的 1,260 条证据仅用于验证 140 × 3 合同覆盖，不能作为生产资料。

## 7. 仍待完成的项目部分

1. 为历史画像 ID 提供经人工审核的一对一映射，并完成置信度校准数据集。
2. 补齐 128 个候选覆盖缺口、处理 15 个未知 ID，并将合规资料人工审核为正式证据边；当前生产已发布证据为 0。
3. 将 BM25、向量检索、图谱遍历接入现有 `EvidenceBundle` 门禁，开展真实召回率、排序和缺证据评测。
4. 实现真实讲义/实操/测试题/项目生成器、代码沙箱、试题质量校验和资源版本存储；当前只有无模型合同夹具。
5. 用真实学生或专家标注数据校准节点能力需求、权重阈值和预计学习时长，当前参数只能证明确定性和单调性。
6. 以 LangChain Tool/LangGraph Node 包装现有纯函数合同，补充状态持久化、幂等重试和人工审核节点，不让框架进入规划内核。
7. PostgreSQL 的画像、路径、资源和审计日志存储；FastAPI 接口和前端路径/资源展示。
8. 扩展到 60 组测试和真实生成实验，再计算幻觉率、难度适配率、召回率、覆盖率和用户演示指标。

## 8. 课程规划协作同学的追加分工

这位同学与我方共同负责“知识图谱事实 -> 路径策略 -> 资源生成输入”的交界面，但不重复知识库同学的资料清洗，也不接管资源生成 Agent 的提示词/模型实现。

| 优先级 | 分配任务 | 主要交付物 | 客观验收 | 协作边界 |
| --- | --- | --- | --- | --- |
| P0 | 图谱关系语义补强 | soft prerequisite、confused/contrasts 关系审计表；每条关系的依据、阈值、review 状态 | 不引入硬先修环；跨章节关系可解释；未知 ID 为 0 | 知识库同学提供证据，该同学负责课程语义与顺序审核，我方维护验证器 |
| P0 | 节点能力需求与资源蓝图校准 | 140 概念的 override 候选、三级预计时长、资源类型/评测类型审核表 | 同章节点不再全部同权；四维需求和为 1；每项有审核依据 | 资源生成同学确认可生产性，我方维护 schema 和不可变目录 |
| P0 | 动态权重离线评测 | 三类画像外的反事实/单调性数据集、阈值敏感性与消融报告 | 降低掌握度/置信度不能降低支持；路径顺序始终不变；参数调整可复算 | 算法同学负责实验方法，该同学负责教育语义，我方维护引擎 |
| P0 | 规划-资源接口联调 | 每个 depth/resource type 的黄金 `ResourceBrief + EvidenceBundle` fixture | 讲义/实操/测试题/项目均能消费；缺证据明确失败；资源侧不能改路径字段 | 与资源生成 Agent 同学共同签字，避免双方各自推断深度 |
| P1 | 章节后更新约束 | 新画像快照到“仅未来节点重算”的状态转移测试 | 已完成/已跳过节点不重算；`path_id` 和顺序不变；新简报只覆盖未完成节点 | 与学情画像/交互导学同学联合 |
| P1 | Agent 包装验收 | LangChain Tool/LangGraph Node 输入输出 schema、幂等键、失败状态测试 | 同输入重试结果 ID 一致；无证据不调用模型；状态可审计 | 智能体搭建同学实现包装，该同学提供课程规划合同测试 |
| P2 | 展示与评测口径 | 路径图、深度、支持强度、证据覆盖的前端/API 字段字典 | 前端展示值均来自已冻结合同；不在前端重新计算权重 | 与前端、测试同学联合 |

我方继续主责：`CoursePlanner`/`NodeWeightEngine`/`ResourceBriefBuilder` 的代码所有权，稳定摘要、路径不变量、合并门禁和端到端回归。协作同学主责数据校准、课程语义审核、跨 Agent 黄金样例和离线评测，不直接修改路径顺序规则。

## 9. 当前验收结果

- 3 类画像均生成 140 节点的同序路径；进阶画像有 10 个高掌握节点标记为 skipped，但节点集合与顺序不变。
- 使用 1,260 条合成已发布证据覆盖 140 × 3 深度，成功构建并校验 410 份 `ResourceBrief`、410 个 `EvidenceBundle`/资源包和 1,500 个结构化资源产物。
- 3 次缺证据场景均明确失败；测试夹具证据绑定率为 100%。
- 以上不能替代生产指标：生产已发布证据仍为 0，尚未开展真实模型生成，因此不报告幻觉率和难度适配率。
