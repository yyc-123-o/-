# 课程规划 Agent 独立运行设计

- 日期：2026-07-31
- 状态：已确认设计，待实施计划
- 范围：独立运行入口、标准事件输入、概念锚点检索、可选 SQLite 会话和端到端验收
- 前置资产：`CoursePlanningAgent`、`ai-course-v1`、710 条候选知识片段、BM25 检索工具

## 1. 背景

课程规划 Agent 已经可以作为 Python 库运行，并能在 LangGraph 中完成初始化、画像刷新、节点完成、去重和重置。但当前调用方必须手动加载课程图谱、节点属性和知识库，构造检索器及 Agent，再自行创建标准事件。仓库 CLI 没有 Agent 命令，验收测试也没有覆盖真实 Agent 与完整知识库的组合。

现有 BM25 会扫描全部候选片段。课程节点查询缺少概念准入门禁，导致 `math.linear-algebra.scalar` 等节点可能召回表情包或扩散模型项目内容。能产生命中不等于命中可信，因此独立运行前必须先解决相关性下限。

当前组员画像样例也不能安全直接适配：缺少图谱版本、掌握度置信度和证据引用，并使用多个复合旧节点。现有画像门禁拒绝这些输入是正确行为，本设计不通过默认值推断或强制一对一映射绕过门禁。

## 2. 目标

- 提供一条可直接调用的 `skillforge-kb agent-run` 命令。
- 自动加载默认课程、关系、节点属性和候选知识库。
- 只接受标准 `PlanningAgentEvent`，复用现有 Pydantic 信任边界。
- 支持无状态内存运行和可选 SQLite 跨进程会话。
- 为课程节点查询增加高置信度概念锚点，阻止宽泛 BM25 误召回。
- 提供可直接运行的标准初始化事件样例和运行手册。
- 增加真实事件、完整图谱和 710 条知识库的端到端验收。

## 3. 非目标

- 不适配或修补当前不完整的组员画像样例。
- 不把复合旧节点强制映射为一个课程概念。
- 不增加 FastAPI、前端或多 Agent 调度。
- 不接入大模型或资源生成模型。
- 不把候选片段转换为正式 `EvidenceRecord` 或 `EvidenceBundle`。
- 不以 SQLite 替代正式画像、路径或证据数据库。

## 4. 方案选择

采用“CLI + 运行时工厂 + 可选 SQLite”方案。

一次性 CLI 虽然简单，但不能跨进程继续同一 `thread_id`。FastAPI 会引入当前不需要的服务部署与接口维护。运行时工厂复用现有领域接口，CLI 负责文件边界和序列化，SQLite 只在明确指定时启用，能覆盖本地演示和可持续会话两个场景。

## 5. 模块边界

### 5.1 独立运行时

新增 `src/skillforge_kb/agents/runtime.py`：

- `StandaloneAgentPaths`：课程、关系、节点属性和知识库路径。
- `load_planning_event(path: Path) -> PlanningAgentEvent`：读取标准 UTF-8 JSON，拒绝非法或额外字段。
- `build_standalone_course_planning_agent(paths, checkpointer=None) -> CoursePlanningAgent`：加载全部只读资产，构造 BM25 和检索工具，编译 LangGraph。
- `run_standalone_event(paths, event, thread_id, checkpointer=None) -> CoursePlanningAgentResult`：运行一个事件并返回标准结果。

运行时不读取全局当前目录、不扫描 `processed/`，也不使用隐藏回退路径。所有默认路径由 CLI 从项目根目录显式传入。

### 5.2 CLI

在 `src/skillforge_kb/cli.py` 增加 `agent-run`：

```text
skillforge-kb agent-run
  --event-file PATH
  --thread-id TEXT
  [--state-db PATH]
  [--output-file PATH]
  [--course-file PATH]
  [--relations-file PATH]
  [--attributes-file PATH]
  [--knowledge-file PATH]
```

默认资产：

- `resources/ontology/ai_course_v1.yaml`
- `resources/ontology/ai_relations_v1.yaml`
- `resources/ontology/concept_attributes_v1.yaml`
- `data/index_chunks.jsonl`

标准输出始终只包含结果 JSON。指定 `--output-file` 时，同一份 JSON 还会以 UTF-8 原子写入文件。输入或配置错误使用退出码 2；Agent 返回 `failed` 状态时先输出完整结果，再使用退出码 3。

### 5.3 SQLite 会话

新增运行依赖 `langgraph-checkpoint-sqlite>=3,<4`，与当前 LangGraph checkpoint 主版本一致。

- 未指定 `--state-db`：使用 `InMemorySaver`，适合一次性调用。
- 指定 `--state-db`：使用 `SqliteSaver`，同一个数据库文件与 `thread_id` 可跨命令恢复状态。
- SQLite 上下文由 CLI 显式打开和关闭。
- 数据库父目录不存在时创建；无法创建、打开或写入时拒绝运行。
- 不允许静默回退到内存模式。
- `.skillforge/` 加入 `.gitignore`，避免本地状态误提交。

`CoursePlanningAgent.create` 和 `build_course_planning_graph` 的 checkpointer 类型扩展为 LangGraph `BaseCheckpointSaver`，默认行为保持 `InMemorySaver`。

## 6. 标准输入契约

CLI 只接受 `PlanningAgentEvent` JSON。初始化事件内嵌标准 `LearnerProfileSnapshot`，其他事件继续使用既有契约：

- `initialize`：必须包含标准画像。
- `profile_refreshed`：必须包含标准画像。
- `concepts_completed`：必须包含非空且唯一的概念 ID。
- `reset`：不能包含画像或完成节点。

新增 `examples/agents/initialize_event.json`，使用当前 `ai-course-v1` 和最小合法零基础画像。示例只用于启动演示，不替代组员画像接口。

不完整组员画像仍由现有适配器稳定拒绝。未来接入前必须由画像负责方提供：明确 `graph_version`、拆分后的单概念 ID、置信度、证据引用和审核后的映射清单。

## 7. 概念锚点检索

`KnowledgeQuery` 增加 `anchors: tuple[str, ...] = ()`。

`build_knowledge_query` 使用当前课程概念的中英文正式名称作为 anchors。别名、摘要、章节、学习目标和深度继续参与 BM25 查询文本，但不参与准入门禁，避免短别名和通用术语扩大召回范围。

检索步骤：

1. 对查询锚点和候选文本进行 NFKC、大小写和空白/标点规范化。
2. 英文锚点按完整词或完整短语匹配，不允许 `RAG` 命中 `storage`。
3. 中文锚点按完整连续短语匹配。
4. 查询没有 anchors 时保持通用 BM25 行为。
5. 查询有 anchors 时，只对至少命中一个锚点的片段计算 BM25。
6. 没有片段通过锚点门禁时返回 `no_results`。

该策略优先保证精度下限，允许知识覆盖不足。数学节点无可靠资料时返回 `no_results`，而不是用无关项目片段填充上下文。

## 8. 输出与错误处理

- 合法事件返回完整 `CoursePlanningAgentResult` JSON。
- 输入 JSON、事件结构、画像结构或资产格式错误：转换为简洁 CLI 参数错误，不打印堆栈。
- Agent 业务状态为 `failed`：先输出完整结果，再以退出码 3 结束。
- 知识库无锚点命中：规划状态保持 `ready`，知识上下文为 `no_results`。
- 检索器受控异常：规划状态保持 `ready`，知识上下文为 `unavailable`。
- SQLite 无法创建、打开或写入：拒绝执行，不回退内存。
- 输出文件不得覆盖事件、图谱、属性或知识库输入。
- 所有候选命中继续带有 `evidence_state=candidate`，不得作为正式引用。

## 9. 测试与验收

### 9.1 检索门禁

- 英文缩写使用完整词边界，`RAG` 不命中 `storage`。
- 中文正式名称使用完整短语匹配。
- 数学当前节点不再返回表情包或扩散模型项目片段。
- RAG、LoRA 等正式名称存在于语料时可返回候选。
- 不带 anchors 的通用 BM25 查询保持现有行为。

### 9.2 运行时与 CLI

- 标准初始化事件样例可构造完整 Agent 并得到 `ready`。
- 输出包含路径、当前节点、适配结果和知识上下文。
- 默认命令不需要 API Key、Docker、Qdrant 或网络。
- 非法 JSON、非标准画像、未知图谱版本和输出覆盖稳定拒绝。
- CLI 标准输出可直接解析为 JSON。

### 9.3 SQLite

- 首次初始化后关闭进程，再使用同一数据库与 `thread_id` 重复提交事件，返回 `event_duplicate=true`。
- 新完成节点事件可从保存状态推进到下一节点。
- reset 跨进程清除会话，随后允许重新初始化。
- SQLite 不可写时命令失败且不生成虚假成功输出。

### 9.4 质量门禁

```text
pytest tests/unit tests/acceptance -q
ruff check src tests
mypy src/skillforge_kb
git diff --check
```

既有单元/验收基线为 365 passed。Docker Testcontainers 集成测试仍由 Docker daemon 环境单独验证，不是独立 Agent 的运行依赖。

## 10. 完成定义

- 新环境执行 `uv sync` 后，可用一条 `agent-run` 命令运行样例事件。
- 无 SQLite 时可以完成一次完整规划；有 SQLite 时可跨进程继续相同会话。
- 数学节点不输出无关候选，可靠知识缺失时明确返回 `no_results`。
- 标准事件、结果和现有 Python API 保持向后兼容。
- 未审核知识、组员旧画像、正式证据和大模型资源生成边界没有被放宽。
