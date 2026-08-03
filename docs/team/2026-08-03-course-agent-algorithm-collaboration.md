# 课程规划 Agent 算法协作清单

## 1. 协作目标

本清单用于算法同学在不破坏课程规划 Agent 稳定合同的前提下，补齐需要论文、标注数据或真实实验支持的算法。每项任务均可独立建分支、测试和提交 Pull Request。

共同开发基线为：

```text
origin/feature/course-agent-kb-retrieval
```

算法 PR 暂时以该分支为目标分支；课程 Agent 整体合入 `main` 后，再统一切换目标分支。

## 2. 已完成基线：不要重复实现

| 能力 | 当前实现 | 状态 |
| --- | --- | --- |
| 稳定课程路径 | `planning/ordering.py`、`planning/planner.py` | 已实现，硬先修拓扑顺序不可被算法重排 |
| 节点支持权重 | `planning/adaptation.py` | 已实现可解释规则基线 |
| 节点权重搜索/消融 | `planning/calibration.py` | 已实现确定性候选搜索、敏感性和消融 |
| 规划策略校准 | `evaluation/planner_calibration.py` | 已实现合成数据上的策略候选排序 |
| 答题更新 | `assessment/update.py` | 已实现幂等规则基线，待研究算法替换 |
| 路径离线评测 | `evaluation/path_evaluation.py` | 已实现合成画像回归评测 |
| 候选知识检索 | `retrieval/bm25.py` | 已实现 BM25 基线和概念锚点门禁 |
| 资源时长与配额 | `resources/allocation.py` | 已实现版本化规则基线 |
| Agent 运行时 | `agents/runtime.py`、`agents/planning_agent.py` | 已实现 LangGraph 状态机、SQLite 和 CLI |

这些实现是后续算法的比较基线和降级路径。新算法不得直接删除或覆盖基线。

## 3. 稳定扩展接口

| 接口 | 输入 | 输出 | 允许变化 | 禁止变化 |
| --- | --- | --- | --- | --- |
| `KnowledgeRetriever.retrieve` | `KnowledgeQuery` | `KnowledgeRetrievalResult` | 检索、融合、重排算法 | 候选变正式证据、取消概念锚点门禁 |
| `CoursePlanner(..., policy)` | 图谱、画像、`PlannerPolicy` | `PathDecision` | 阈值和能力权重候选 | 概念集合、硬先修、稳定顺序 |
| `NodeWeightEngine(..., node_policy)` | 画像、路径节点 | `NodeAdaptationDecision` | 支持度/工作量参数 | 路径增删、跳过先修、完成节点重算 |
| `apply_assessment_event` 合同 | `AssessmentLedger`、`AssessmentEvent` | `AssessmentUpdateResult` | 掌握度估计算法 | 事件幂等、证据引用、画像版本 |
| `allocate_resources` | 节点适配、蓝图、分配策略 | `ResourceAllocation` | 时间和配额参数 | 下游重新推断深度或修改路径 |

如任务需要新增协议，先提交只包含模型/协议/合同测试的 PR，再提交算法实现 PR。

## 4. 待认领算法任务

### ALG-CP-01：BKT 掌握度估计器（P0，需要论文）

目标：在保留规则更新器作为降级路径的同时，实现版本化 Bayesian Knowledge Tracing 更新器。

- 输入：现有 `AssessmentLedger`、`AssessmentEvent` 和课程概念 ID。
- 输出：现有 `AssessmentUpdateResult`，包含掌握度、置信度、错误模式和事件审计。
- 建议文件：`src/skillforge_kb/assessment/bkt.py`、`tests/unit/assessment/test_bkt.py`。
- 必须支持：冷启动、guess/slip/learn 参数、连续答对/答错、提示和重试、可选时间衰减、事件重放幂等。
- 对照基线：`apply_assessment_event`。
- 指标：Brier Score、Log Loss、ECE；在无真实数据时只能报告合成或专家标注结果。
- 验收：相同输入和参数输出完全一致；所有概率在 `[0,1]`；重复事件不产生第二次更新；失败时显式降级到规则基线。

### ALG-CP-02：IRT 与自适应选题（P0，需要论文）

目标：实现可解释的 2PL IRT 基线和基于信息增益/后验不确定性的题目选择。

- 第一份 PR：题目参数、候选题和选择决策合同，不实现复杂模型。
- 第二份 PR：2PL 能力估计及参数校准。
- 第三份 PR：自适应选题与随机/固定难度基线对比。
- 建议文件：`assessment/irt.py`、`assessment/adaptive_testing.py` 及对应测试。
- 必须输出：题目 ID、目标概念、评分分项、预期信息增益和原因码。
- 约束：题目必须绑定课程概念；不得选择未满足硬先修范围之外的诊断题；题库不足时显式降级。
- 指标：能力估计误差、平均题量、后验不确定性、概念覆盖率、硬先修违规率 `0`。

### ALG-CP-03：专家标注策略校准（P0，需要数据与统计设计）

目标：把现有合成数据回归门禁扩展为专家标注的节点支持度、教学深度和跳过决策校准。

- 复用：`NodeWeightCalibrationDataset`、`search_node_weight_policies`、`search_planner_policies`。
- 交付：数据字典、标注说明、双人标注一致性报告、训练/验证划分和版本摘要。
- 禁止：用测试集选择参数；把合成结果表述为真实教学效果；直接改生产默认策略。
- 指标：标注一致性、支持强度准确率、深度准确率、跳过准确率、低置信度保守率、硬先修违规率 `0`。
- 提升流程：候选报告 -> 教育语义审核 -> 独立验证集 -> 单独策略版本 PR。

### ALG-IR-01：混合检索与重排（P1，需要检索实验）

目标：在 `KnowledgeRetriever` 协议下实现 BM25、向量检索和受限图谱扩展的可降级融合。

- 实现必须返回现有 `KnowledgeRetrievalResult`，保持 `evidence_state=candidate`。
- 推荐基线：BM25；候选方案：向量召回、RRF、受限一跳扩展、来源质量/难度/多样性重排。
- 数据：至少 150 条人工标注查询，记录概念 ID、相关 chunk 和标注人。
- 指标：Recall@5、MRR@10、nDCG@10、零命中率、P95 延迟。
- 验收：向量服务不可用时回退 BM25；通用词不得绕过概念锚点；不得读取 pickle/FAISS 旧索引作为生产依赖。

### ALG-CP-04：学习时长和资源配额校准（P1，需要数据）

目标：校准 `ResourceAllocationPolicy` 中的时长倍数与练习/测评配额，不改变资源类型和路径合同。

- 输入：`ResourceBrief`、节点适配结果、专家估时或脱敏学习日志。
- 输出：候选 `ResourceAllocationPolicy`、版本摘要和校准报告。
- 对照基线：`allocate_resources` 当前规则策略。
- 指标：时长 MAE、配额覆盖率、完成率或专家一致性；无真实日志时不得报告学习效果。
- 验收：时长为正并按既有粒度取整；支持需求提高不能减少资源；未请求资源类型配额保持零。

### ALG-KG-01：软关系候选发现（P2，需要人工审核）

目标：发现 `soft_prerequisite`、`confused_with` 和 `contrasts_with` 候选关系。

- 可用方法：术语共现、概念相似度、错误混淆统计或链路预测。
- 输出必须是独立候选报告，包含 source、target、relation、score、证据 chunk 和算法版本。
- 禁止自动写入 `ai_relations_v1.yaml` 或 Neo4j 正式图谱。
- 验收：概念 ID 全部合法；候选可追溯；人工审核前发布边数量保持零。

## 5. 建议两人分工

| 算法同学 | 主任务 | 次任务 |
| --- | --- | --- |
| 算法同学 A | `ALG-CP-01` BKT、`ALG-CP-02` IRT/自适应选题 | 协助 `ALG-CP-03` 标注与概率校准 |
| 算法同学 B | `ALG-IR-01` 混合检索、`ALG-CP-03` 策略校准 | 协助 `ALG-CP-04` 时长/配额校准 |

`ALG-KG-01` 在 P0/P1 完成后再由算法同学 B 与知识库同学共同开展。

## 6. 每项任务的完成定义

算法任务只有同时满足以下条件才算完成：

1. 有输入输出合同、假设、适用边界和降级策略。
2. 有论文或方法依据，但不以论文链接代替实现。
3. 有同数据、同指标的基线比较和消融。
4. 有可重复命令、随机种子、数据版本和结果摘要。
5. 有单元测试、边界测试和课程不变量测试。
6. Ruff、mypy、单元与验收测试通过。
7. Pull Request 说明是否使用合成、专家标注或真实数据。
8. 未改变课程图谱事实、路径稳定性和证据审核边界。

## 7. 开发命令

```powershell
git fetch origin
git switch -c alg/cp-01-bkt-mastery origin/feature/course-agent-kb-retrieval
uv sync --frozen --dev
uv run pytest tests/unit tests/acceptance -q
uv run ruff check src tests scripts
uv run mypy src/skillforge_kb
```

详细分支、数据与 Pull Request 规则见仓库根目录 `CONTRIBUTING.md`。
