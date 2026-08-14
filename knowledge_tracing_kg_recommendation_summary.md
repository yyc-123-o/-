# 知识追踪与知识图谱学习路径推荐功能总结

## 0. 项目现有基础与我们的工作起点

### 0.1 项目目前已经写出来的东西

当前 SkillForge 项目已经不是空项目，它已经有一套确定性的课程规划和学习者画像基础。我们这次的知识追踪和路径推荐实现，是在这些已有能力上继续往下做的。

项目已有基础包括：

```text
1. 课程知识图谱
   - 使用 OntologyCatalog 读取课程概念和关系。
   - 已有 AI 课程图谱资源文件。
   - 已有 hard_prerequisite 等先修关系校验。

2. 学习者画像
   - 使用 LearnerProfileSnapshot 表示学生状态。
   - 已有 knowledge_mastery、abilities、error_patterns、preferences 等字段。
   - 规划器已经会读取学生画像来判断跳过、补救、学习深度。

3. 规则式测评更新
   - 已有 AssessmentEvent、AssessmentLedger、AssessmentUpdateResult。
   - 已有 apply_assessment_event 规则基线。
   - 规则基线可以根据答对/答错、提示、重试、作答时间更新 mastery、confidence 和 error_patterns。

4. 确定性课程规划器
   - 已有 CoursePlanner。
   - 能根据课程图谱和学生画像生成完整课程路径。
   - 会保留硬先修顺序，不随意改变 path order。

5. 节点适配和权重评估
   - 已有 NodeWeightEngine。
   - 能为路径节点计算 readiness、support、delivery depth 等规划信号。

6. 资源生成桥接
   - 已有 ResourceBrief、EvidenceBundle 等资源生成契约。
   - 当前规划结果可以继续传给后续资源生成 Agent。
```

### 0.2 我们是基于什么继续做的

我们的实现不是另写一套孤立系统，而是基于项目已有的这些接口继续增强：

```text
AssessmentEvent
AssessmentLedger
AssessmentUpdateResult
LearnerProfileSnapshot
OntologyCatalog
CoursePlanner
NodeWeightEngine
```

也就是说，原项目已有的链路是：

```text
学生答题事件
  -> 规则式 assessment 更新
  -> 更新 LearnerProfileSnapshot
  -> CoursePlanner 重新规划或更新路径
```

我们在这个基础上增强成：

```text
学生答题事件
  -> BKT 知识追踪
  -> 时间遗忘修正
  -> 错误风险和置信度更新
  -> 写回 LearnerProfileSnapshot
  -> CoursePlanner 读取新画像
  -> 结合知识图谱关系做学习路径推荐
```

### 0.3 我们替换和增强的部分

原来的规则式更新逻辑适合作为工程基线，但它的问题是：

```text
1. 掌握度变化主要是规则加减分，不是真正的概率追踪。
2. 没有明确区分“原始掌握度”和“长期未练后的有效掌握度”。
3. 对题目难度、题目区分度、作答时间的利用还比较弱。
4. 对知识图谱中的 confused_with、contrasts_with 等关系利用不足。
5. 推荐更偏路径规划结果，缺少基于 KT 状态的图谱解释型推荐。
```

所以我们当前新增的核心能力是：

```text
1. 用 BKT 替代单纯规则加减分，估计每个知识点的 mastery_score。
2. 用 forgetting-aware effective_mastery 表示学生当前真正可用的掌握度。
3. 用 hint、retry、response_time、item difficulty、discrimination 修正观测可信度。
4. 用 error_risk 和 error_patterns 表示学生在每个概念上的错误风险。
5. 用知识图谱中的 hard_prerequisite、soft_prerequisite、confused_with、contrasts_with 做推荐。
6. 输出 reason_codes、relation_kinds、explanation_paths，让推荐结果可解释。
```

### 0.4 当前边界

由于当前开发要求是：

```text
只在新创建的单文件里实现，不改项目其他文件。
```

所以目前的实现状态是：

```text
已经能调用项目已有模型和规划器；
已经能作为单文件增强模块运行；
还没有正式替换 assessment 包默认导出；
还没有接入 PlanningAgent、CLI 或 API 默认流程。
```

如果后续允许修改主流程，可以把当前入口接入到：

```text
assessment 包导出
PlanningAgent 测评后重规划流程
CLI / API 的 assessment update 命令
前端学习路径推荐接口
```

## 1. 功能定位

当前实现位于：

```text
src/skillforge_kb/assessment/knowledge_tracing_experimental.py
```

这个文件实现的是一条实验性的、但已经能和项目核心模型对接的学习闭环：

```text
学生答题记录
  -> BKT 知识追踪
  -> 更新学生掌握度画像
  -> 结合课程知识图谱
  -> 输出可解释的学习路径推荐和补救队列
```

它的职责是把学生的测评反馈转成规划器可以消费的学习者状态和推荐信号。

它不负责：

```text
修改课程图谱
修改 CoursePlanner
重排原始 PathDecision
跳过硬先修
生成资源内容
```

## 2. 已实现的核心能力

### 2.1 BKT 知识追踪

入口：

```python
KnowledgeTracingEngine
apply_bkt_assessment_event(...)
```

作用：

```text
根据学生答题事件更新知识点掌握度、置信度和错误风险。
```

当前考虑的因素：

```text
答对 / 答错
提示次数
重试次数
作答时间
题目难度
题目区分度
知识点难度
遗忘衰减
错误类型
```

输出会写入项目已有的：

```text
LearnerProfileSnapshot.knowledge_mastery
LearnerProfileSnapshot.error_patterns
```

### 2.2 批量学习记录回放

入口：

```python
replay_bkt_assessment_events(...)
```

作用：

```text
把一段学生答题历史按时间顺序回放，得到最终学习者画像和 KT 状态事实表。
```

适用场景：

```text
导入历史测评记录
回放一轮学习会话
离线构建学生当前知识状态
```

### 2.3 KT 状态事实表

入口：

```python
kt_state_facts(...)
```

作用：

```text
输出每个已追踪知识点的可审计 KT 状态。
```

每条事实包含：

```text
concept_id
mastery_score
effective_mastery
confidence
error_risk
evidence_count
model_version
parameter_version
input_snapshot_digest
reason_codes
updated_at
```

### 2.4 路径规划支持报告

入口：

```python
build_kt_planning_support_report(...)
```

作用：

```text
调用现有 CoursePlanner 和 NodeWeightEngine，
把 KT 后的学生状态转成规划侧能用的支持信号。
```

输出包括：

```text
当前可学节点
需要补救的节点
被硬先修阻塞的节点数量
每个路径节点的支持强度
每个路径节点的 readiness/support 信息
```

### 2.5 基于知识图谱的学习路径推荐

入口：

```python
recommend_kg_learning_path(...)
```

作用：

```text
基于学生 KT 状态和课程知识图谱，推荐下一批学习概念。
```

使用的知识图谱关系：

```text
hard_prerequisite
soft_prerequisite
confused_with
contrasts_with
```

推荐原则：

```text
硬先修未满足时，优先推荐硬先修缺口
存在易混淆概念时，加入辨析型推荐
目标概念被阻塞时，标记为 blocked_target
所有推荐都输出 reason_codes 和 explanation_paths
```

## 3. 主要输入

### 3.1 课程知识图谱

类型：

```python
OntologyCatalog
```

提供：

```text
concepts
course graph version
hard_prerequisite relations
soft_prerequisite relations
confused_with relations
contrasts_with relations
concept difficulty
```

### 3.2 学生画像

类型：

```python
LearnerProfileSnapshot
```

主要字段：

```text
profile_id
graph_version
knowledge_mastery
abilities
error_patterns
preferences
```

### 3.3 评估账本

类型：

```python
AssessmentLedger
```

主要字段：

```text
profile
processed_event_ids
```

### 3.4 单次答题事件

类型：

```python
AssessmentEvent
```

主要字段：

```text
event_id
profile_id
graph_version
concept_ids
correct
response_time_ms
hint_count
attempt_count
timestamp
error_kind
evidence_refs
```

### 3.5 多条答题事件

类型：

```python
Sequence[AssessmentEvent]
```

用于批量回放：

```python
replay_bkt_assessment_events(...)
```

### 3.6 可选题目元数据

类型：

```python
AssessmentItemMetadata
```

字段：

```text
item_id
difficulty
discrimination
target_depth
expected_time_ms
```

作用：

```text
让 BKT 更新能够感知题目难度、题目区分度和作答时间是否异常。
```

### 3.7 可选学习目标

类型：

```python
target_concept_ids: Sequence[str]
```

示例：

```text
dl.cnn.convolution
```

作用：

```text
让知识图谱推荐围绕目标知识点展开，优先处理目标的先修缺口和易混淆概念。
```

## 4. 主要输出

### 4.1 单次 KT 更新输出

类型：

```python
AssessmentUpdateResult
```

包含：

```text
ledger
policy_version
policy_digest
event_digest
applied
affected_concept_ids
mastery_before
mastery_after
classified_error_kind
reason_codes
```

作用：

```text
与项目现有 assessment.update.apply_assessment_event 的返回模型保持兼容。
```

### 4.2 批量回放输出

类型：

```python
ProjectKTBatchUpdateResult
```

包含：

```text
final_ledger
event_results
kt_state_facts
applied_count
duplicate_count
reason_codes
```

### 4.3 KT 状态事实输出

类型：

```python
KTStateFact
```

包含：

```text
concept_id
mastery_score
effective_mastery
confidence
error_risk
evidence_count
model_version
parameter_version
input_snapshot_digest
reason_codes
updated_at
```

### 4.4 路径规划支持报告

类型：

```python
ProjectKTPlanningSupportReport
```

包含：

```text
schema_version
profile_id
graph_version
generated_at
path_id
kt_policy_version
path_node_count
signals
remediation_queue
available_queue
blocked_count
reason_codes
```

### 4.5 知识图谱学习路径推荐报告

类型：

```python
KGLearningPathRecommendationReport
```

包含：

```text
schema_version
profile_id
graph_version
generated_at
policy_version
policy_digest
target_concept_ids
recommendations
blocked_target_ids
reason_codes
```

每条推荐：

```text
concept_id
rank
score
path_status
recommendation_kind
target_concept_ids
prerequisite_gap_ids
relation_kinds
explanation_paths
mastery_score
effective_mastery
confidence
error_risk
reason_codes
```

## 5. 推荐逻辑说明

### 5.1 基础逻辑

推荐函数会先读取学生当前 KT 状态：

```text
mastery_score
effective_mastery
confidence
error_risk
```

再读取课程知识图谱中的关系：

```text
hard_prerequisite
soft_prerequisite
confused_with
contrasts_with
```

然后结合 CoursePlanner 的路径状态：

```text
available
pending
blocked
skipped
completed
```

最终输出推荐队列。

### 5.2 推荐排序因素

当前 KG 推荐分数由这些因素组成：

```text
mastery_gap
confidence_gap
error_risk
prerequisite_gap
soft_prerequisite relation
confused_with relation
contrasts_with relation
path_availability
```

### 5.3 推荐类型

当前会输出这些 recommendation_kind：

```text
remediate_prerequisite
relation_neighbor
learn_target
learn_next
review_weak
blocked_target
```

## 6. 示例

输入目标：

```text
dl.cnn.convolution
```

如果学生还没有掌握它的硬先修，输出可能是：

```text
1. dl.vision.image-tensor
   recommendation_kind: remediate_prerequisite
   reason_codes:
     - target_prerequisite_gap

2. dl.cnn.cross-correlation
   recommendation_kind: relation_neighbor
   relation_kinds:
     - confused_with
   explanation_paths:
     - dl.cnn.convolution -[confused_with]-> dl.cnn.cross-correlation

3. dl.cnn.convolution
   recommendation_kind: blocked_target
   prerequisite_gap_ids:
     - dl.vision.image-tensor
```

## 7. 和系统的衔接情况

当前已经衔接：

```text
OntologyCatalog
LearnerProfileSnapshot
AssessmentLedger
AssessmentEvent
AssessmentUpdateResult
CoursePlanner
NodeWeightEngine
```

当前还没有正式接入：

```text
assessment 包导出
PlanningAgent 默认流程
CLI 命令
API 接口
资源生成 Agent
```

原因是当前开发边界要求只在这个单文件内工作。

## 8. 一句话总结

这个功能的输入是：

```text
学生画像 + 学生答题事件 + 课程知识图谱 + 可选学习目标 + 可选题目元数据
```

输出是：

```text
更新后的学生掌握度画像 + KT 状态事实 + 规划支持报告 + 基于知识图谱的可解释学习路径推荐
```

## 9. 引用文章与吸收的方法

> 引用依据核查时间：2026-08-14。下面列出的论文不是简单堆砌参考文献，而是说明“我们为什么这样设计知识追踪和基于知识图谱的路径推荐”。

### 9.0 论文依据总览

| 方向 | 引用文章 | 核心方法 | 我们采用的方式 | 对应实现 |
| --- | --- | --- | --- | --- |
| 知识追踪主模型 | Corbett & Anderson, *Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge* | 用隐变量表示学生是否掌握知识点，通过 guess/slip/learn 参数做贝叶斯更新 | 把每个 `concept_id` 作为一个可追踪知识点，答题后更新掌握概率 | `KnowledgeTracingEngine` / `bkt_posterior` / `bkt_learning_transition` |
| 时间遗忘 | Qiu et al., *Does Time Matter? Modeling the Effect of Time with Bayesian Knowledge Tracing* | 在 BKT 中考虑时间间隔，避免长期未练习仍被视为完全掌握 | 保留原始 `mastery_score`，额外计算会随时间衰减的 `effective_mastery` | `ForgettingParameters` / `effective_mastery` |
| 可解释基线模型 | Pavlik, Cen & Koedinger, *Performance Factors Analysis: A New Alternative to Knowledge Tracing* | 用历史成功次数和失败次数预测下一次表现 | 作为可解释 baseline 和后续离线调参模型，不替代主链路 BKT | `PFAParameters` / `evaluate_pfa_sequence` / `compare_bkt_and_pfa` |
| 知识图谱推荐 | Wang et al., *KGAT: Knowledge Graph Attention Network for Recommendation* | 推荐时利用知识图谱高阶邻居，不同关系的重要性不同 | 不引入神经网络，改成可审计的 relation-aware scoring | `KGLearningPathPolicy` / `_score_kg_candidate` |
| 学习路径推荐综述 | Li, Li & Gao, *Personalized Learning Path Recommendation Based on Knowledge Graphs: A Survey* | 学习路径要结合知识单元、先修关系、语义依赖和学习者状态 | 把 hard prerequisite 作为硬约束，把软关系作为排序和解释信号 | `recommend_kg_learning_path` |
| 可解释学习路径 | *Explainable Learning Paths Recommendation Based on Knowledge Graph* | 学习路径推荐需要给出图谱路径解释，缓解推荐不透明和学习迷航 | 每条推荐输出 `relation_kinds`、`explanation_paths`、`reason_codes` | `KGLearningPathRecommendation` |
| 图谱路径推理 | Xian et al., *Reinforcement Knowledge Graph Reasoning for Explainable Recommendation* | 推荐结果由 KG 中的显式推理路径支撑 | 不使用强化学习，但吸收“路径即解释”的思想，输出确定性解释路径 | `_kg_relation_candidate_map` / `explanation_paths` |

### 9.0.1 这些论文方法对当前项目的直接价值

```text
BKT 解决：如何把一次次答题转成学生对每个知识点的掌握概率。
Time-aware BKT 解决：如何处理学过但很久没练的知识点。
PFA 解决：如何用成功/失败历史做简单、可解释、可调参的对照模型。
KGAT 解决：如何让知识图谱中的不同关系以不同权重影响推荐。
KG 学习路径综述解决：如何把先修关系和学习目标组织成路径规划问题。
可解释学习路径论文解决：为什么推荐结果必须能说清楚原因。
PGPR 解决：为什么 KG 推荐不能只给分数，还要保留路径证据。
```

### 9.0.2 当前实现没有照搬的部分

```text
没有直接实现 DKT / DKVMN / GNN / RL 等深度模型。
原因不是这些方法没价值，而是当前项目阶段更需要：

1. 小数据可运行；
2. 输出可解释；
3. 能和现有 CoursePlanner 兼容；
4. 不绕过 hard_prerequisite；
5. 每次推荐都能审计 reason_codes 和 explanation_paths。
```

### 9.1 Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge

文章：

```text
Corbett, A. T., & Anderson, J. R.
Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge.
User Modeling and User-Adapted Interaction, 1995.
```

链接：

```text
https://link.springer.com/article/10.1007/BF01099821
```

核心思想：

```text
把每个知识点建模为“已掌握 / 未掌握”的隐状态。
学生每次答题后，通过贝叶斯更新估计该知识点的掌握概率。
```

我们吸收的方法：

```text
1. 每个 concept 单独维护 mastery_score。
2. 使用 prior_mastery / learn_probability / guess_probability / slip_probability。
3. 每次 AssessmentEvent 到来时，先做观测后验更新，再做学习转移。
4. 输出 mastery_before 和 mastery_after，保证每次画像变化可审计。
```

对应实现：

```python
BKTParameters
KnowledgeTracingEngine
bkt_posterior(...)
bkt_learning_transition(...)
apply_bkt_assessment_event(...)
```

### 9.2 Does Time Matter? Modeling the Effect of Time with Bayesian Knowledge Tracing

文章：

```text
Qiu, Y., Qi, Y., Lu, H., Pardos, Z. A., & Heffernan, N. T.
Does Time Matter? Modeling the Effect of Time with Bayesian Knowledge Tracing.
Educational Data Mining, 2011.
```

链接：

```text
https://educationaldatamining.org/EDM2011/wp-content/uploads/proc/edm2011_paper5_full_Qiu.pdf
```

核心思想：

```text
传统 BKT 忽略了时间间隔。
学生长时间没有练习某个知识点时，掌握度应该出现遗忘或有效性下降。
```

我们吸收的方法：

```text
1. 不直接删除历史 mastery_score。
2. 单独计算 effective_mastery。
3. effective_mastery 会根据距离上次观测的时间进行指数衰减。
4. 证据越多、置信度越高，遗忘衰减越慢。
```

对应实现：

```python
ForgettingParameters
KnowledgeTracingEngine.effective_mastery(...)
kt_state_facts(...)
planning_feature_table(...)
```

### 9.3 Performance Factors Analysis: A New Alternative to Knowledge Tracing

文章：

```text
Pavlik Jr., P. I., Cen, H., & Koedinger, K. R.
Performance Factors Analysis: A New Alternative to Knowledge Tracing.
Frontiers in Artificial Intelligence and Applications, 2009.
```

链接：

```text
https://files.eric.ed.gov/fulltext/ED506305.pdf
```

核心思想：

```text
不只看当前一次答题，而是把同一知识点的历史成功次数和失败次数作为预测特征。
PFA 是可解释的、适合早期数据量不大的学习建模基线。
```

我们吸收的方法：

```text
1. 增加 PFA baseline，不替代主链路 BKT。
2. 用 successes / failures 预测下一次答题正确率。
3. 保留 evaluate 和 grid search，后续有真实日志后可以做模型选择。
```

对应实现：

```python
PFAParameters
PFAConceptState
evaluate_pfa_sequence(...)
grid_search_pfa_parameters(...)
compare_bkt_and_pfa(...)
```

### 9.4 KGAT: Knowledge Graph Attention Network for Recommendation

文章：

```text
Wang, X., He, X., Cao, Y., Liu, M., & Chua, T.-S.
KGAT: Knowledge Graph Attention Network for Recommendation.
KDD, 2019.
```

链接：

```text
https://arxiv.org/abs/1905.07854
https://dl.acm.org/doi/10.1145/3292500.3330989
```

核心思想：

```text
推荐不能只依赖用户-物品交互。
知识图谱中的关系和高阶邻居也应该参与推荐。
不同邻居关系的重要性不同，需要有类似 attention 的区分能力。
```

我们吸收的方法：

```text
1. 不直接实现神经网络版 KGAT，因为当前项目更需要可解释、可审计、数据量要求低的算法。
2. 将 KGAT 的“关系重要性不同”工程化为 relation-aware scoring。
3. 对 hard_prerequisite、soft_prerequisite、confused_with、contrasts_with 使用不同权重。
4. 输出 relation_kinds 和 explanation_paths，保留推荐解释。
```

对应实现：

```python
KGLearningPathPolicy
recommend_kg_learning_path(...)
_kg_relation_candidate_map(...)
_kg_relation_priority(...)
_score_kg_candidate(...)
```

### 9.5 Knowledge Graph Based Learning Path Recommendation

文章：

```text
Personalized Learning Path Recommendation Based on Knowledge Graphs: A Survey.
Electronics, 2026.
```

链接：

```text
https://www.mdpi.com/2079-9292/15/1/238
```

核心思想：

```text
基于知识图谱的学习路径推荐需要显式建模知识点之间的先修关系和语义依赖。
学习路径不仅要个性化，还要透明、可解释、适应学习者状态。
```

我们吸收的方法：

```text
1. 把课程知识点视为图谱节点。
2. 把 hard_prerequisite 作为硬约束，而不是普通排序信号。
3. 把 soft_prerequisite、confused_with、contrasts_with 作为推荐排序和解释信号。
4. 推荐结果必须能说明“为什么推荐这个知识点”。
```

对应实现：

```python
recommend_kg_learning_path(...)
KGLearningPathRecommendation
KGLearningPathRecommendationReport
```

### 9.6 Explainable Learning Path Recommendation Based on Knowledge Graph

文章：

```text
Explainable Learning Paths Recommendation Based on Knowledge Graph.
```

链接：

```text
https://www.sciopen.com/article/10.3969/j.issn.1009-8097.2024.07.014
```

核心思想：

```text
学习路径推荐不能只给出结果，还要给出推荐解释。
可解释路径可以缓解学习者迷航和推荐不透明问题。
```

我们吸收的方法：

```text
1. 推荐输出中加入 explanation_paths。
2. 每条推荐保留 relation_kinds。
3. 每条推荐保留 reason_codes。
4. 对目标概念、先修概念、易混淆概念分别标记 recommendation_kind。
```

对应实现：

```python
KGLearningPathRecommendation.explanation_paths
KGLearningPathRecommendation.relation_kinds
KGLearningPathRecommendation.reason_codes
```

### 9.7 Reinforcement Knowledge Graph Reasoning for Explainable Recommendation

文章：

```text
Xian, Y., Fu, Z., Muthukrishnan, S., de Melo, G., & Zhang, Y.
Reinforcement Knowledge Graph Reasoning for Explainable Recommendation.
SIGIR, 2019.
```

链接：

```text
https://arxiv.org/abs/1906.05237
```

核心思想：

```text
推荐系统可以在知识图谱中显式搜索推理路径。
推荐结果应由可解释的 KG 路径支撑，而不仅是一个黑盒分数。
```

我们吸收的方法：

```text
1. 没有直接引入强化学习，因为当前项目更需要确定性和可复现。
2. 吸收“路径解释”的思想，把 KG 关系路径写入 explanation_paths。
3. 保持推荐结果的可审计性和可复现性。
```

对应实现：

```python
_kg_relation_candidate_map(...)
KGLearningPathRecommendation.explanation_paths
```

## 10. 方法如何落到当前项目

### 10.1 知识追踪层

论文方法：

```text
BKT + time-aware forgetting + PFA baseline
```

项目落地：

```text
AssessmentEvent
  -> BKT 更新
  -> LearnerProfileSnapshot.knowledge_mastery
  -> LearnerProfileSnapshot.error_patterns
  -> KTStateFact
```

核心收益：

```text
学生画像不再只是规则加减分，而是有概率模型、遗忘、置信度和错误风险。
```

### 10.2 知识图谱推荐层

论文方法：

```text
KG relation-aware recommendation
KG explainable path reasoning
learning path prerequisite constraint
```

项目落地：

```text
LearnerProfileSnapshot
  -> KTStateFact
  -> OntologyCatalog relations
  -> recommend_kg_learning_path(...)
  -> KGLearningPathRecommendationReport
```

核心收益：

```text
推荐路径不再只是当前 planner 的线性可学节点，
而是能围绕学习目标，从知识图谱中找出：

1. 必须先补的硬先修；
2. 值得辅助学习的软先修；
3. 容易混淆、需要辨析的相关概念；
4. 与目标形成对比、有助于理解边界的概念。
```

### 10.3 为什么没有直接实现深度模型

没有直接实现 KGAT、深度 KT 或强化学习路径搜索，原因是：

```text
1. 当前项目真实学生日志不足；
2. 比赛阶段更需要稳定、可解释、可审计；
3. 现有 CoursePlanner 已经有强约束路径主干；
4. 硬先修不能被黑盒模型绕过；
5. 推荐输出必须带 reason_codes 和 explanation_paths。
```

因此当前选择的是：

```text
论文思想工程化
而不是论文模型原样照搬
```

## 11. 当前实现吸收的核心方法总结

| 来源 | 核心方法 | 当前实现 |
| --- | --- | --- |
| BKT | 贝叶斯掌握度追踪 | `KnowledgeTracingEngine` |
| Time-aware BKT | 时间遗忘衰减 | `effective_mastery` |
| PFA | 历史成功/失败作为预测特征 | `PFAParameters` / `evaluate_pfa_sequence` |
| KGAT | 不同 KG 关系重要性不同 | `KGLearningPathPolicy` 关系权重 |
| KG Learning Path Survey | 先修关系和语义依赖决定路径 | `recommend_kg_learning_path` |
| Explainable KG Recommendation | 推荐要输出解释路径 | `explanation_paths` |
| PGPR | KG 路径支撑推荐解释 | 确定性 `explanation_paths`，不使用 RL |
