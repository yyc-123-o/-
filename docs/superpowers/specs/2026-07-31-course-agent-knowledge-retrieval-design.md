# 课程规划 Agent 知识库检索接入设计

- 日期：2026-07-31
- 状态：已确认设计，待实施计划
- 范围：将远端知识库的 JSONL 片段以只读候选检索方式接入 `CoursePlanningAgent`
- 前置资产：`ai-course-v1` 课程图谱、现有 LangGraph 规划 Agent、远端提交 `08d3151`

## 1. 背景

远端 `main` 新增了一组知识库索引文件：

- `data/index_chunks.jsonl`：710 条知识片段；
- `data/index_bm25.pkl`：BM25 序列化对象；
- `data/index_chunks.pkl`：片段序列化对象；
- `data/index_faiss.index`：FAISS 索引。

四个文件与本地 `processed/` 中已有文件的 Git 对象哈希一致。当前代码已有确定性的课程路径规划、节点适配和 LangGraph Agent，但正式 `EvidenceIndex` 仍为空，且上传 JSONL 不包含课程概念 ID、来源 URL、许可证或人工审核信息。

本设计只把 JSONL 作为候选知识检索语料，不把它直接提升为正式证据，也不让检索结果改变路径规划事实。

## 2. 目标

- 为 `CoursePlanningAgent` 增加当前学习节点的知识片段检索能力。
- 通过 LangChain `StructuredTool` 公开检索工具，保留未来替换为向量或混合检索的接口。
- 使用安全、可复现、无外部服务依赖的 JSONL 加载和 BM25 基线。
- 对中文和英文术语提供稳定的混合分词与排序。
- 将检索结果、语料摘要和失败状态纳入 Agent 输出，便于后续资源生成 Agent 消费。
- 保持已有路径 ID、节点集合、顺序、深度、适配结果和规划审计摘要不变。

## 3. 非目标

- 不加载或反序列化 `pickle` 文件。
- 不读取或依赖 FAISS 索引，也不推断其生成模型。
- 不在本阶段引入 Qdrant、Embedding 模型、Reranker、API Key 或网络服务。
- 不把候选片段转换为 `EvidenceRecord`，不绕过来源、许可证和人工审核门禁。
- 不让检索结果增删、重排或跳过课程图谱节点。
- 不实现资源生成、领域检索 Agent 之间的跨 Agent 调度。

## 4. 方案比较

### 4.1 直接加载 pickle 与 FAISS

优点是接入速度快，可以复用上传者生成的索引。缺点是 `pickle` 可能触发任意代码执行，FAISS 文件没有记录查询编码模型，无法证明与当前配置兼容，也难以在测试和新环境中复现。因此不采用。

### 4.2 从 JSONL 重建 BM25（本阶段采用）

该方案只读取结构化文本，索引构建确定性强，不需要模型或服务。通过检索器协议隔离实现细节，后续可以替换成混合检索而不改变 Agent 契约。对专业术语、模型名、代码命令和中英文混合文本具有可靠的关键词基线。

### 4.3 BM25 + 向量混合检索

该方案的语义召回上限更高，但需要固定 Embedding 模型、向量索引重建策略和运行时服务，超出当前接入的最小闭环。本阶段只保留可替换接口，后续单独设计和评测。

## 5. 模块边界

新增 `src/skillforge_kb/retrieval/`：

- `models.py`：严格的数据契约，包括 `KnowledgeChunk`、`KnowledgeQuery`、`KnowledgeHit`、`KnowledgeRetrievalResult` 和检索状态。
- `corpus.py`：按行读取 JSONL，校验必填字段、枚举值、重复片段 ID，计算稳定的语料摘要；任何格式错误都以行号报告，禁止部分加载。
- `bm25.py`：对标题、章节路径和正文构建确定性 BM25 索引，负责分词、召回、Top-K 限制和稳定 Tie-break。
- `tool.py`：定义检索器协议和 `KnowledgeRetrievalTool`，提供 Python 调用接口以及 LangChain `StructuredTool` 适配器。
- `__init__.py`：只导出稳定的公共接口。

修改：

- `src/skillforge_kb/agents/planning_agent.py`：接收可选检索器，在当前节点确定后调用检索工具。
- `src/skillforge_kb/agents/planning_agent_models.py`：在状态和结果中增加可选的知识上下文字段；保持原有规划字段和事件契约有效。
- `src/skillforge_kb/agents/__init__.py`：导出检索工具与模型。
- `tests/unit/retrieval/`：检索模块单元测试。
- `tests/unit/agents/test_planning_agent.py`：Agent 自动调用、无结果、异常降级和路径不变测试。

知识库运行入口使用 `data/index_chunks.jsonl`。如果调用方传入其他路径，必须显式构造语料对象；Agent 不扫描工作区、不自动读取 `processed/`，避免隐式依赖用户本地数据。

## 6. 数据契约

### 6.1 输入片段

每一行必须包含：

```text
chunk_id: non-empty string
doc_id: non-empty string
source_title: non-empty string
heading_path: list[string]
text: non-empty string
page_no: integer or null
domain_tag: non-empty string
difficulty: 入门 | 进阶 | 高阶
token_count: non-negative integer
```

加载器额外保证：

- `chunk_id` 不重复；
- `heading_path` 的元素均为非空字符串；
- `page_no` 为正整数或 `null`；
- `token_count` 只作为原始元数据，不被当作真实 tokenizer 计数；
- 每条文本保留原文，不修改其内容；
- 语料摘要由规范化 JSONL 行按顺序计算 SHA-256。

### 6.2 查询

查询至少包含：

```text
query: non-empty string
top_k: 1..20
```

课程 Agent 构造的查询由当前概念的中英文名称、别名、摘要、章节标题、学习目标和 `delivery_depth` 组成，不包含完整画像原文或敏感个人信息。

### 6.3 命中和结果

每个 `KnowledgeHit` 包含片段 ID、文档 ID、来源标题、章节路径、原文、难度和 BM25 分数，并带有固定的 `candidate` 证据状态。结果包含查询、概念 ID、语料摘要、命中序列和以下状态之一：

- `ok`：至少有一个命中；
- `no_results`：语料有效但没有命中；
- `unavailable`：加载或查询期间发生受控异常。

由于输入没有来源 URL、许可证和审核人，命中结果不能直接构造 `EvidenceRecord` 或 `EvidenceBundle`。

## 7. Agent 数据流

```text
PlanningAgentEvent
        |
        v
规划路径 -> 节点适配 -> 选择唯一当前节点
                              |
                              v
                 生成节点查询 -> KnowledgeRetrievalTool
                              |
                              v
                 knowledge_context(candidate hits)
                              |
                              v
               CoursePlanningAgentResult
```

- 初始化和画像刷新在选出当前节点后检索一次。
- 完成节点事件触发路径更新后，针对新的当前节点重新检索。
- 重复事件复用已检查点中的知识上下文。
- 重置事件清空知识上下文。
- 课程已完成时知识上下文为空。
- 检索节点是规划流程的辅助节点；无结果或异常不会把规划状态改为 `FAILED`。
- `path_id`、`planning_audit`、`adaptations` 和节点状态不读取检索分数，因此检索开启前后规划结果必须保持一致。

`CoursePlanningAgent.create(...)` 增加一个可选的检索器参数。未传入时保持现有行为，结果中的知识上下文为空；传入时由 LangGraph 节点调用检索器的 LangChain 工具接口。

## 8. 安全和错误处理

- JSONL 使用标准 JSON 解析和 Pydantic 校验，不执行任何内容。
- 禁止在生产代码中调用 `pickle.load` 或等价反序列化。
- 任意坏行、重复 ID 或非法枚举导致语料加载失败，并包含文件路径和行号；不返回部分索引。
- 查询参数非法时由输入模型拒绝。
- 检索器异常被转换为 `unavailable` 结果，保留可审计错误码和消息，不泄漏堆栈。
- 空语料和零命中使用 `no_results`，不视为课程规划失败。
- 检索内容只能作为候选上下文展示或供下游审核，不能绕过正式证据发布门禁。

## 9. 测试与验收

### 9.1 检索模块

- 合法 710 行语料可完整加载并生成稳定摘要。
- 缺字段、非法类型、非法难度、重复 ID 和损坏 JSON 行均稳定拒绝。
- 中文词、英文缩写、模型名和代码命令可召回相关片段。
- 相同输入多次查询结果字节级一致；分数相同按 `chunk_id` 稳定排序。
- `top_k` 边界、空语料和无命中状态均有覆盖。

### 9.2 Agent 接入

- 注入一个记录调用次数的测试检索器，验证当前节点确定后只调用一次。
- 验证检索命中会出现在结果知识上下文中。
- 验证无结果和检索异常不改变 `path_id`、节点顺序、节点集合、适配结果和规划审计。
- 验证重复、重置、画像刷新和课程完成的上下文生命周期。
- 验证不注入检索器时所有现有行为不变。

### 9.3 质量门禁

实施完成后运行：

```text
pytest -q
ruff check src tests
mypy src/skillforge_kb
```

预期所有既有测试及新增测试通过。涉及 Docker 的 Postgres/Neo4j 测试只在服务可用时运行，不能以外部服务缺失替代单元测试证据。

## 10. 明确不变的边界

- 课程图谱仍是章节、概念、先修和教学顺序的唯一事实源。
- `CoursePlanner` 和 `NodeWeightEngine` 不读取知识库文本。
- 正式证据仍必须经过来源、许可证、概念、深度和人工审核门禁。
- 资源生成 Agent 仍只消费 `ResourceBrief + EvidenceBundle`，本阶段不把候选检索结果直接传给它。
- 后续向量混合检索必须另行提供模型版本、索引版本、评测结果和回滚方案。
