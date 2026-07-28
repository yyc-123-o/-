# SkillForge 课程知识图谱设计

- 日期：2026-07-27
- 最后修订：2026-07-28（加入学情画像兼容边界）
- 状态：已确认，v1 已实现（Neo4j 集成依赖本机 Docker/服务）
- 适用范围：课程规划 Agent 的知识结构底座
- 教学范围：高校本科生，机器学习基础到大语言模型前沿

## 1. 目标

本阶段建设课程知识图谱及其只读学情画像输入契约，不实现课程规划 Agent、个性化路径算法、资源生成、多 Agent 编排或前端。

图谱必须同时满足三个目标：

1. 用章节、小节和稳定概念节点表达课程结构；
2. 用无环先修关系表达合理的学习逻辑与顺序；
3. 为每个概念提供入门、进阶、专业三个学习深度，供后续课程规划 Agent 选择。

知识图谱结构必须独立于尚未完成审核的证据切片。课程结构和先修关系由团队人工策划并审核；现有自动概念标签只能作为映射建议，不能直接生成正式节点或边。

## 2. 现有知识库条件审计

### 2.1 可复用资产

- 主知识库有 1,423 条候选切片、30 个来源和 14 个模块；
- 中文教学资料包含线性代数、概率与信息论、数值计算、机器学习基础、前馈网络、正则化、优化、CNN 和实践方法论的明确章节结构；
- S1 论文覆盖 Attention、BERT、GPT-3、RLHF、LoRA、RAG 和 RAGAS 等后半段核心主题；
- 项目已有双语名称、稳定概念 ID、引用、难度和内容类型等领域契约；
- 开发环境已配置 Neo4j 5.26，能够作为正式图数据库；
- 既有设计已明确 PostgreSQL 是证据事实来源，Neo4j 只保存已审核知识结构和关系。

### 2.2 质量限制

- 1,423 条主库切片均为 `candidate`，尚未完成人工审核；
- 当前只有 27 个自动概念标签，低于项目 120-180 个核心概念的目标；
- 自动标签存在跨主题误标，不能据此自动推断先修关系；
- 873 条英文切片存在单词粘连，435 条存在规范哈希不一致；
- 旧库 710 条切片全部缺少完整来源，不得生成正式证据关系；
- 当前融合结果不可发布，旧 pickle、BM25 和 FAISS 文件不得加载到运行时。

### 2.3 审计结论

现有资产足以构建人工策划的课程结构图谱 v1，并为大部分概念标记候选证据覆盖情况；现有资产不足以自动生成可信图谱，也不足以发布正式证据关系。

因此图谱建设采用“课程主干先行、证据审核后挂接”的边界：

- 课程、章节、小节、概念、深度和先修关系可先构建并人工审核；
- 候选证据只记录覆盖状态，不写入正式 Neo4j 证据边；
- 只有 `human_reviewed` 或 `published` 的证据切片才能在后续发布阶段与概念建立正式关联。

## 3. 方案决策

### 3.1 淘汰：自动标签直接建图

优点是速度快，缺点是会把误标、覆盖偏差和错误先修关系固化到课程规划结果中，不满足可信要求。

### 3.2 采用：人工课程主干加审核后证据映射

团队先定义章节、概念和先修 DAG，再用现有切片生成候选覆盖报告。图谱逻辑可以独立验证，证据质量问题不会阻塞课程结构建设，也不会污染正式关系。

### 3.3 后续：模型辅助扩容

大模型可以提出新概念、别名和候选关系，但所有结果必须进入人工审核队列。该能力不属于图谱 v1。

## 4. 图谱架构

```text
Course
  `- HAS_CHAPTER {order}
      Chapter
        `- HAS_SECTION {order}
            Section
              `- TEACHES {order, required}
                  Concept
                    `- HAS_LEVEL
                        ConceptLevel
                          intro | intermediate | advanced

Concept - PREREQUISITE_OF {kind, min_mastery} -> Concept
Concept - PART_OF --------------------------------> Concept
Concept - CONTRASTS_WITH --------------------------> Concept
Concept - CONFUSED_WITH ---------------------------> Concept
```

课程层级负责“在哪一章、按什么顺序教”；概念关系负责“学习什么、依赖什么”。二者不得混用：章节顺序不能替代先修关系，先修关系也不能隐式决定所有展示顺序。

后续课程规划采用以下确定性规则：

1. 先按 `PREREQUISITE_OF` 对必修概念执行拓扑排序；
2. 对不存在依赖顺序的概念，按章节、小节和 `TEACHES.order` 稳定排序；
3. 根据学习者能力选择对应 `ConceptLevel`；
4. 已掌握概念可以跳过，但它的后继节点仍保留；
5. 软先修可用于补充建议，不能阻断主路径。

本阶段只保证图谱支持这些查询，不实现上述路径算法。

## 5. 节点模型

### 5.1 Course

| 字段 | 约束 |
| --- | --- |
| `id` | 固定为 `course.ai-foundations-to-llm.v1` |
| `title_zh` / `title_en` | 必填 |
| `audience` | 高校本科生 |
| `version` | 固定版本字符串 |
| `status` | `draft`、`reviewed` 或 `published` |

### 5.2 Chapter

| 字段 | 约束 |
| --- | --- |
| `id` | `chapter.<两位序号>.<slug>` |
| `order` | 从 1 开始连续且唯一 |
| `title_zh` / `title_en` | 必填 |
| `summary` | 说明本章边界，不得只重复标题 |
| `learning_outcomes` | 至少 2 项可验证目标 |
| `core` | 是否属于重点深做模块 |

### 5.3 Section

| 字段 | 约束 |
| --- | --- |
| `id` | 以所属章节 ID 为前缀 |
| `order` | 在所属章节内从 1 开始连续且唯一 |
| `title_zh` / `title_en` | 必填 |
| `learning_outcomes` | 至少 1 项 |

### 5.4 Concept

| 字段 | 约束 |
| --- | --- |
| `id` | 小写 ASCII 分层 ID，发布后不可复用或静默改义 |
| `names.zh` / `names.en` | 双语名称必填 |
| `aliases` | 中英文别名列表，跨概念不得冲突 |
| `summary` | 一句话界定概念边界 |
| `difficulty` | 1-4 的结构难度 |
| `required` | 是否属于课程主路径 |
| `evidence_status` | `candidate_supported`、`coverage_gap` 或 `published` |
| `review_status` | `draft`、`reviewed` 或 `published` |

每个概念必须且只能有一个主教学小节。跨章节复用通过概念关系表达，不复制语义相同的节点。

### 5.5 ConceptLevel

每个概念固定包含三个深度节点：

| 等级 | 面向对象 | 必填内容 |
| --- | --- | --- |
| `intro` | 零基础或基础薄弱 | 直观解释、关键术语、简单示例、最低掌握标准 |
| `intermediate` | 有相关基础 | 原理、公式或算法步骤、可运行练习、常见错误 |
| `advanced` | 进阶学习者 | 推导、局限、复杂实践或论文延伸、较高掌握标准 |

深度节点保存 `learning_outcomes`、`mastery_threshold` 和 `assessment_kinds`。深度不是三个不同概念，也不改变概念的先修语义。

## 6. 关系模型

| 关系 | 方向 | 用途 |
| --- | --- | --- |
| `HAS_CHAPTER` | Course -> Chapter | 课程章节和顺序 |
| `HAS_SECTION` | Chapter -> Section | 章内层级和顺序 |
| `TEACHES` | Section -> Concept | 主教学位置、章内顺序、必修标记 |
| `HAS_LEVEL` | Concept -> ConceptLevel | 三档教学深度 |
| `PREREQUISITE_OF` | 前置概念 -> 后继概念 | 严格或建议先修 |
| `PART_OF` | 子概念 -> 复合概念 | 知识组成关系 |
| `CONTRASTS_WITH` | Concept <-> Concept | 方法对比 |
| `CONFUSED_WITH` | Concept <-> Concept | 易混淆关系 |

`PREREQUISITE_OF.kind` 只能为：

- `hard`：未达到 `min_mastery` 时不能进入后继概念；
- `soft`：推荐先学，但不得阻断主路径。

`min_mastery` 是 0-1 之间的闭区间数值。图谱 v1 中，`published` 证据状态只能用于存在已审核证据记录的概念；其余概念必须保持 `candidate_supported` 或 `coverage_gap`。

对称关系在规范文件中只写一次，发布器负责生成一致的 Neo4j 表达。所有关系必须携带图谱版本和人工审核状态。

## 7. 课程章节主干

| 顺序 | 章节 | 预计概念数 | 深做 |
| ---: | --- | ---: | --- |
| 1 | 数学与数值计算基础 | 12 | 否 |
| 2 | 经典机器学习与模型评估 | 16 | 是 |
| 3 | 神经网络与反向传播 | 12 | 否 |
| 4 | 优化、正则化与训练策略 | 16 | 否 |
| 5 | CNN 与表示学习概览 | 10 | 否 |
| 6 | 嵌入表示与序列建模基础 | 10 | 否 |
| 7 | Transformer 核心原理 | 16 | 是 |
| 8 | 大语言模型预训练与提示学习 | 12 | 是 |
| 9 | 模型对齐与参数高效微调 | 12 | 是 |
| 10 | RAG 检索增强生成 | 14 | 是 |
| 11 | RAG 评测与综合实训 | 10 | 是 |

目标规模为约 140 个概念，允许在人工编目时处于 120-160 个范围内。超过 160 个概念或增加第 12 章必须重新评审范围。

### 7.1 关键主路径

图谱必须至少保证以下路径完整且无环：

```text
向量与矩阵运算
  -> 梯度与优化
  -> 神经网络与反向传播
  -> 嵌入表示
  -> 注意力与自注意力
  -> Transformer
  -> 语言模型与预训练
  -> 向量检索
  -> RAG
  -> RAG 评测
```

经典机器学习分支必须覆盖监督学习、线性回归、逻辑回归、损失函数、训练/验证/测试划分、过拟合、分类指标和模型选择。Transformer 分支必须覆盖位置编码、缩放点积注意力、多头注意力、前馈子层、残差连接、归一化和编码器/解码器。LLM/RAG 分支必须覆盖 BERT/GPT、提示与上下文学习、SFT、RLHF、LoRA、嵌入、索引、召回、重排、生成和 RAGAS 类评测。

## 8. 规范文件与代码边界

计划实现下列独立组件：

```text
resources/ontology/
  ai_course_v1.yaml          人工维护的课程、章节、小节和概念目录
  ai_relations_v1.yaml       先修、组成、对比和易混淆关系
  legacy_profile_ids_v1.yaml 经人工审核的一对一画像 ID 映射

src/skillforge_kb/ontology/
  models.py                  Pydantic 图谱契约
  catalog.py                 YAML 加载、查询和稳定排序
  validation.py              结构、DAG、章节和路径校验
  coverage.py                候选证据覆盖报告，不发布证据边
  profile.py                 画像快照契约和只读 ProfileAdapter
  neo4j.py                   参数化、幂等的 Neo4j 发布适配器
```

课程目录是版本控制下的事实来源。Neo4j 是发布面，不允许在数据库界面中手工修改后再反向覆盖 YAML。

图谱发布器只处理课程结构，不读取 pickle 或旧 FAISS/BM25 索引。候选覆盖分析只读取 JSONL 文本字段和元数据，不反序列化任何遗留二进制文件。

## 9. 数据流

```text
人工课程规范 YAML
        |
        v
严格 Schema 校验
        |
        v
章节顺序 + 唯一性 + DAG + 可达性校验
        |
        +------> 失败报告，禁止发布
        |
        v
候选 JSONL 概念覆盖对照
        |
        +------> candidate_supported / coverage_gap 报告
        |
        v
幂等发布到 Neo4j
        |
        v
节点/边计数与关键路径验收报告
```

自动概念映射结果只改变覆盖报告，不得修改人工维护的课程顺序和先修边。

## 10. 校验与异常处理

以下任一条件成立时，验证命令必须失败且不得连接 Neo4j 写入：

- 课程、章节、小节或概念 ID 重复；
- 双语名称缺失，或别名被两个概念占用；
- 章节或小节顺序不连续；
- 必修概念没有唯一主教学小节；
- 任一概念缺少三个深度节点；
- 关系引用未知概念；
- 严格先修关系存在环；
- 硬先修的章节、小节和教学顺序不早于后继概念；
- 必修概念无法从课程根节点到达；
- 关键主路径断裂；
- `published` 证据状态没有已审核证据记录支撑。

Neo4j 发布使用事务和稳定 ID 执行 `MERGE`。重复发布同一版本必须得到相同节点数、边数和属性；发布失败时 YAML 事实来源不受影响，下一次可以完整重试。

## 11. 测试策略

### 11.1 单元测试

- 合法课程目录可以加载并稳定排序；
- 重复 ID、重复别名、未知引用和缺失双语名称被拒绝；
- 章节和小节序号必须连续；
- 每个概念恰好包含三个深度等级；
- 严格先修环、悬空边和逆序硬先修被拒绝；
- 对称关系不会重复；
- 关键路径完整且所有必修概念可达；
- 候选标签只能生成覆盖建议，不能生成正式图谱边。

### 11.2 集成测试

- 对空 Neo4j 发布一次后，节点、关系和约束数量符合规范；
- 相同版本连续发布两次，节点和关系数量不增加；
- 查询 RAG 的直接和间接先修，能够返回 Transformer、嵌入和向量检索路径；
- 非法目录在建立 Neo4j 会话前即失败；
- Neo4j 不可用时返回明确错误，不修改本地规范文件。

Docker 不可用时，单元测试和静态图谱验证仍必须完整运行；Neo4j 集成测试可以明确标记为环境阻塞，不能伪报通过。

## 12. 验收标准

课程知识图谱 v1 只有同时满足以下条件才算完成：

1. 包含 11 个顺序固定的章节和 120-160 个双语概念；
2. 每个章节至少包含 2 个小节和明确学习目标；
3. 每个概念都有唯一主教学位置和三个深度节点；
4. 所有严格先修关系构成 DAG，未知引用和悬空节点为 0；
5. 所有必修概念从课程根节点可达；
6. 数学到 RAG 评测的关键主路径查询通过；
7. 自动标签生成正式关系的数量为 0；
8. 输出候选证据覆盖率和 `coverage_gap` 清单；
9. Neo4j 发布器使用参数化查询并通过幂等测试；
10. 单元测试、Ruff 和 mypy 通过，Neo4j 集成测试结果如实记录；
11. 图谱 Schema、维护方法、验证命令和导入命令有文档说明。
12. 学情画像必须通过版本化适配契约与图谱概念 ID 对齐；未映射、复合或歧义节点必须使整个适配失败。

## 13. 明确不在本阶段范围内

- 课程规划 Agent 和学习路径推荐算法；
- 学习者画像建模、掌握度更新和自适应测试的算法实现；仅定义课程图谱所消费的只读画像输入契约；
- LangGraph 智能体状态机；
- 讲义、实操指南和测试题生成；
- 多 Agent 辩论和裁判协议；
- 未审核证据发布、Qdrant 重建和 Evidence API 扩展；
- 前端图谱可视化和可运行代码环境；
- 最新论文的实时检索或自动扩图。

## 14. 后续接口边界

课程规划 Agent 后续只能通过版本化图谱接口读取：

- 有序章节和小节；
- 概念及三个学习深度；
- 直接和传递先修关系；
- 必修、选修和覆盖缺口状态。

Agent 不得直接修改 Neo4j 图谱，也不得从未审核切片动态创造正式先修边。图谱修改必须先更新 YAML、通过校验、完成代码评审，再发布新版本。

## 15. 学情画像兼容边界

### 15.1 设计目的

学情诊断组当前样例同时包含诊断事实、路径状态和资源生成提示。课程图谱只消费可审计的诊断事实，不能把路径或资源结论反向当作图谱事实。

因此，课程规划前必须通过 `ProfileAdapter` 将外部画像转换为 `LearnerProfileSnapshot`。适配器是纯转换与校验组件：不调用大模型、不修改 Neo4j、不重算掌握度、不创建路径。

```text
原始画像 JSON
       |
       v
ProfileAdapter + 版本化 ID 映射表
       |
       +----> 映射或结构错误：拒绝并报告字段路径
       |
       v
LearnerProfileSnapshot
       |
       +----> 课程图谱：先修、章节和三级深度
       |
       v
后续 PathDecision
       |
       v
后续 ResourceBrief
```

### 15.2 `LearnerProfileSnapshot` 最小契约

```text
schema_version: learner-profile.v1
profile_id: 不可变快照 ID
learner_ref: 伪匿名学习者引用，不使用姓名或学号
graph_version: 对应课程图谱版本
observed_at: 本次诊断观察时间
generated_at: 快照生成时间
assessment_runs: 诊断批次 ID 与测试版本
knowledge_mastery[]:
  concept_id: 图谱中的 Concept.id
  mastery_score: 0-1，未测评时为 null
  assessment_status: assessed | not_assessed
  confidence: 0-1
  observed_at: 该概念最近一次有效测评时间
  evidence_refs: 测评批次、题目或答题记录的稳定 ID
abilities:
  theoretical_understanding | coding_ability | mathematical_foundation | problem_solving
  每项均包含 score、confidence 和 assessment_run_id
error_patterns[]:
  code、count、ratio、concept_ids、evidence_refs
preferences:
  content_order、code_language、framework、presentation、pace、project_orientation
```

`knowledge_point` 等展示名称由图谱根据 `concept_id` 解析，画像中不得保存可变的概念名称副本。`not_assessed` 不得伪装成低掌握度分数。

### 15.3 ID 对齐规则

1. `concept_id` 必须精确匹配当前图谱的 `Concept.id`；
2. 现有 `KG-ML-*`、`KG-DL-*` 只允许通过随版本提交的显式映射表转换；
3. 映射必须为一对一；一个旧节点合并多个知识点时不得复制掌握度，必须由画像组拆分节点或重新测评；
4. 映射表每条记录包含 `legacy_id`、`concept_id`、`graph_version` 和人工审核人；
5. 不允许依据中文名称、嵌入相似度或大模型猜测概念映射；
6. 不存在映射、映射到已废弃概念、图谱版本不一致或发现复合节点时，适配器必须失败并返回字段路径；
7. `current_chapter`、`previous_chapter` 必须使用图谱 `Chapter.id`，不得自定义 `ch03_cnn` 等本地编号。

当前样例中的“线性回归与梯度下降”“决策树与随机森林”“反向传播与优化器”“Transformer 与注意力机制”均属于复合节点，在拆分前不能进入正式 `LearnerProfileSnapshot`。

### 15.4 路径和资源的职责分离

以下字段不属于画像快照，必须从诊断输出移出：

- `recommendation`、`depth_prescription`：由课程规划策略计算；
- `learning_path_context`：由课程规划 Agent 产生并作为 `PathDecision` 保存；
- `resource_generation_hints`：由资源生成前的 `ResourceBrief` 产生；
- `predecessor_nodes`、`successor_nodes`：只能由课程图谱查询，不能由画像手写；
- `next_nodes` 的带说明字符串：替换为结构化 `PathDecision` 节点列表。

`PathDecision` 至少包含 `path_id`、`profile_id`、`graph_version`、`policy_version`、有序 `concept_id`、节点状态、为未完成节点选择的 `delivery_depth`、硬先修阻塞项和可追溯决策原因。

初次生成后，主路径的概念集合与顺序保持不变。每章完成后的画像更新仅允许调整尚未完成节点的 `delivery_depth` 和资源呈现方式；不得自行新增、删除或重排主路径节点。

### 15.5 硬先修与深度选择规则

课程规划 Agent 后续必须按以下顺序决策：

1. 读取已版本对齐的 `LearnerProfileSnapshot`；
2. 读取目标概念全部 `hard` 先修及其 `min_mastery`；
3. 任何硬先修为 `not_assessed`、置信度不足或掌握度低于阈值时，将其列为阻塞项，不能直接选择目标概念的进阶或专业深度；
4. 仅在目标概念及硬先修满足策略阈值时，才基于能力维度和偏好选择 `intro`、`intermediate` 或 `advanced`；
5. `skip` 只能由版本化策略产生，且必须记录掌握度、置信度、先修检查和策略版本；
6. 原“quick_review”改为面向当前节点的 `compact_instruction` 或 `scaffolded_instruction`，不新增独立复习模式。

课程规划策略的具体阈值和算法不属于本阶段，但上述约束必须由后续实现测试覆盖。

### 15.6 画像适配测试

- 已知 `legacy_id` 能映射到指定 `Concept.id`；
- 未映射、歧义或版本不匹配的 ID 被拒绝；
- `unexplored` / `not_assessed` 不能转换为任意数值掌握度；
- 展示名称与前驱、后继字段不会覆盖图谱事实；
- 原画像中的 `recommendation` 和 `depth_prescription` 被移除，适配器不产生 CNN 进阶层等路径决策；
- 画像快照不含路径和资源生成字段；
- 同一原始画像和映射表重复适配时产生相同的规范快照和审计报告；
- 伪匿名学习者引用之外的直接身份字段不进入课程规划输入。

“CNN 掌握度不足或反向传播等硬先修未达标时不能选择 CNN 进阶层”保留为后续课程规划实现的契约测试，不由本阶段的 `ProfileAdapter` 执行。
