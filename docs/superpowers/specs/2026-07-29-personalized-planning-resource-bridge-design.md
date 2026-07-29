# SkillForge 个性化规划与资源生成桥接设计

- 日期：2026-07-29
- 状态：已审计，进入实施
- 适用范围：画像适配、节点动态权重、资源蓝图、ResourceBrief 与证据检索边界
- 前置资产：`ai-course-v1` 课程图谱、`LearnerProfileSnapshot`、确定性 `CoursePlanner`

## 1. 背景与问题

当前仓库已经具备可信的课程结构图谱和确定性规划内核，但资源生成闭环仍缺少三条连接：

1. 外部画像无法通过空的 legacy ID 映射表完整转换为标准画像；现有适配器只保留知识掌握度，丢失能力、错误模式和偏好。
2. 图谱没有正式的已审核证据索引，全部 140 个概念仍处于 `coverage_gap`，资源生成无法按概念、深度和语言检索可审计来源。
3. 规划内核只有全局固定能力权重，没有节点能力需求、错误风险和资源支持强度，也没有将稳定路径转换为资源生成输入的契约。

本设计补齐这些边界，但不改变已确认的主路径约束：硬先修和课程教学顺序决定路径集合与顺序，动态权重只影响未完成节点的资源支持策略。

## 2. 设计目标

- 将组员画像样例转换为版本一致、证据可追溯的标准画像快照。
- 建立候选证据到已审核证据的显式门禁，禁止未审核内容进入正式资源检索。
- 用确定性、可解释、版本化的节点适配策略计算资源关注度和支持强度。
- 由规划侧生成只读 `ResourceBrief`，使资源生成 Agent 不需要重新推断课程深度和先修关系。
- 为讲义、实操指南和分阶测试题提供统一证据过滤与验收约束。
- 保持既有 `PathDecision` 的路径 ID、节点集合、顺序和已完成节点不变。

## 3. 非目标

- 不在规划内核中调用大模型、向量检索、Neo4j 或网络。
- 不让动态权重重排、删除或新增主路径节点。
- 不把 learner-specific 分数、资源提示或生成文本写入静态课程图谱。
- 不在本阶段实现完整多 Agent 辩论、裁判、前端和在线掌握度诊断。

## 4. 分层架构

```text
Raw learner export --ProfileAdapter--> LearnerProfileSnapshot
                                             |
OntologyCatalog --CoursePlanner-----------> PathDecision
       |                                     |
       +-- ConceptAttributes/Blueprints ---> NodeAdaptation
                                             |
Approved EvidenceIndex -----------------> ResourceBriefBuilder
                                             |
                                             v
                                  ResourceBrief + EvidenceBundle
                                             |
                                             v
                                  Resource Generation Agent
```

事实源职责：

- `OntologyCatalog`：章节、概念、深度、先修和静态资源属性。
- `LearnerProfileSnapshot`：掌握度、能力、错误模式、学习偏好和证据引用。
- `PlannerPolicy`/`NodeWeightPolicy`：版本化阈值、权重和适配规则。
- `EvidenceIndex`：来源、片段、许可证、定位符、审核状态和概念/深度绑定。
- `PathDecision`：稳定课程路径，不承载生成文本。
- `ResourceBrief`：面向资源生成的只读任务描述。

## 5. 标准画像适配

`ProfileAdapter` 必须适配以下字段：

- `knowledge_mastery`：通过已审核的一对一 legacy ID 映射；复合旧 ID 不复制掌握度，必须拆分或拒绝。
- `abilities`：理论理解、编程能力、数学基础、问题解决四维分数与置信度。
- `error_patterns`：错误模式代码、比例、涉及概念和证据引用。
- `preferences`：内容顺序、代码语言、框架、呈现方式、学习时长和项目导向。
- `assessment_runs`、`evidence_refs` 和时间字段。

适配器继续拒绝 `learning_path_context`、`resource_generation_hints`、`prior_chapter_performance` 和任何 `depth_prescription`。这些字段属于下游派生结果，不能倒灌为画像事实。

## 6. 证据索引与发布门禁

证据记录至少包含：

```text
evidence_id, source_id, chunk_id, concept_id, depth_level
source_url, locator, license_status, normalized_hash
language, content_kind, difficulty
review_status, reviewed_by, reviewed_at
```

状态流转：`candidate -> reviewed -> published`，另有 `rejected` 和 `revoked` 终态。

- `candidate` 只进入覆盖报告和人工审核队列。
- 只有许可证明确、来源 URL 和 locator 存在、hash 可校验且人工审核完成的 `published` 记录可被 `EvidenceBundle` 查询。
- 每个已发布证据必须绑定一个存在于当前图谱版本的 concept 和 depth。
- 资源生成查询默认过滤 `graph_version`、`review_status=published`、语言、资源类型和深度。

正式图谱结构与证据索引保持逻辑解耦；证据可以先存 governed manifest 或 PostgreSQL/Qdrant 索引，只有审核通过的摘要边允许进入 Neo4j。

## 7. 节点动态适配

主路径保持不变。对每个未完成节点计算：

```text
ability_fit = sum(learner_ability[d] * concept_ability_demand[d])
readiness = 0.60 * effective_mastery + 0.40 * ability_fit
support_need = 0.55 * mastery_gap + 0.25 * relevant_error_risk + 0.20 * ability_gap
```

其中 `concept_ability_demand` 是版本化静态属性，四维权重和为 1；`effective_mastery` 同时考虑掌握度、置信度和测评状态。缺失或低置信度时不虚构高能力，资源支持至少为 `scaffolded`。

输出 `NodeAdaptationDecision`：

```text
concept_id
readiness_score
support_need_score
support_intensity: compact | standard | scaffolded | remediation
factor_contributions[]
reason_codes[]
adaptation_digest
```

偏好只改变资源形式和节奏，不改变 `skipped`、`delivery_depth`、硬阻塞和路径顺序。硬先修阻塞时只能生成补救型入门资源。

## 8. ResourceBrief

`ResourceBriefBuilder` 输入 `PathDecision`、`OntologyCatalog`、标准画像和节点适配结果，输出：

```text
request_version
brief_id
path_id
graph_version
profile_id
policy_digest
concept_id
chapter_id
section_id
sequence
status
delivery_depth
learning_outcomes
assessment_kinds
hard_prerequisites
blocking_prerequisites
soft_prerequisites
related_confusions
required_resource_types
node_adaptation
error_pattern_hints
presentation_preferences
evidence_filters
citation_requirements
acceptance_checks
```

`brief_id` 由以上规范化字段和 `adaptation_digest` 计算；不包含生成时间。`skipped` 节点不生成资源简报，`completed` 节点只允许审计读取，不重新生成资源。

资源 Agent 只能消费 `ResourceBrief + EvidenceBundle`：

- 讲义必须覆盖当前深度 learning outcomes，并绑定概念级证据。
- 实操指南必须符合代码语言、框架和运行检查，关键 API/结论绑定证据。
- 测试题必须符合 assessment kinds、目标难度和错误模式覆盖，并提供答案依据。
- 任何证据不足、版本不一致或引用不可定位都必须返回结构化失败，不得用模型知识补齐来源。

## 9. 验收标准

- 示例画像可成功适配为完整标准快照，能力、错误模式和偏好不丢失。
- 画像未知、复合、重复或版本不一致时稳定拒绝。
- 证据覆盖报告按 concept x depth x language x content_kind 输出，未审核记录不能查询。
- 三类画像在相同图谱上得到可复算的节点适配分数；改变能力只影响未完成节点的适配/深度，不改变路径集合和顺序。
- 所有必修 concept level 都能生成 schema-valid `ResourceBrief` 骨架。
- `ResourceBrief` 不包含生成文本，不允许资源 Agent 覆盖路径字段。
- 同一输入的路径、适配结果和简报字节级稳定；策略变化产生新的 digest。
- 现有图谱验证、规划测试、Ruff 和 mypy 全部保持通过。

## 10. 实施顺序

1. 完成画像映射与完整适配。
2. 建立证据记录、审核门禁和覆盖矩阵。
3. 补齐概念能力属性与三层资源蓝图。
4. 实现 `NodeWeightEngine` 和适配摘要。
5. 实现 `ResourceBrief` 与 `ResourceBriefBuilder`。
6. 实现 `EvidenceBundle` 查询和资源生成 Agent 适配层。
7. 增加章节后反馈、审核编排和全链路评测。
