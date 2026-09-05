# 织知成径项目设计总览

## 1. 项目一句话

织知成径是一个 AI 课程知识库治理与多智能体学习规划平台。它不是普通聊天机器人，也不是单纯课程学习页面，而是把课程资料、知识图谱、学习者画像、课程规划、证据检索、资源生成和测评反馈连成一条闭环。

核心链路：

```text
课程资料采集
-> 文档清洗与知识库构建
-> 课程知识图谱与先修关系
-> 学情诊断与学习者画像
-> 个性化课程规划
-> 领域证据检索
-> 课程资源生成
-> 测评反馈与掌握度更新
-> 再次规划
```

## 2. 对外应该讲的核心能力

1. 课程知识库治理：把 PDF、HTML、讲义、课程文档变成可追溯、可审核、可复用的知识资产。
2. 知识图谱与先修关系：维护知识点、章节、能力要求和先修依赖，约束学习路径不能乱跳。
3. 学情诊断与学习者画像：通过基础信息、自适应测试、答题记录和学习行为形成当前掌握状态。
4. 个性化课程规划：CoursePlanner 根据画像和图谱生成学习路径，决定跳过、补救、学习、实践等状态。
5. 多智能体协作：规划 Agent、检索 Agent、资源生成 Agent、反馈 Agent 分工完成学习任务。
6. 证据约束的资源生成：讲义、练习、测验、项目任务都要绑定证据、引用、许可证和审核状态。
7. 测评反馈闭环：测评和练习结果更新掌握度，再触发下一轮路径规划。

## 3. 用户角色

- 课程建设者：上传和治理课程资料，维护知识库、知识图谱和证据来源。
- 教师与教学管理者：查看学习者画像、知识盲区、规划建议和资源生成结果。
- 学习者：获得个性化学习路径、补救内容、练习、测评和反馈。
- 学校与机构：统一管理课程资产，追踪课程运行质量，支持规模化智能教学。

## 4. 当前前端页面地图

- `/`：公共产品宣传首页，面向未登录用户，负责品牌、价值、能力和开始入口。
- `/login`：登录页，目前前端模拟登录，提交后进入 `/app`。
- `/register`：注册页，目前前端模拟注册，提交后进入 `/app`。
- `/app`：登录后工作台首页，展示平台进程、待处理事项、最近活动、接口状态和当前任务。
- `/dashboard`：重定向到 `/app`。
- `/knowledge-base`：重定向到 `/resources#knowledge-base`。
- `/planning`：重定向到 `/learning-path`。
- `/diagnosis`：学情诊断概览。
- `/diagnosis/basic`：基础信息与学习背景录入。
- `/diagnosis/assessment`：自适应知识水平评估。
- `/profile`：学习者画像详情。
- `/learning-path`：课程规划与路径地图。
- `/resources`：资源中心，包含知识库与课程资源。
- `/assessment`：测评与反馈。
- `/history`：学习历史。
- `/profile/settings`：个人中心与设置。

## 5. 前端技术栈

位置：`frontend/web`

- Vue 3 + `<script setup>`
- TypeScript
- Vite
- Vue Router
- Pinia
- Axios
- ECharts
- Lucide 图标
- markdown-it + KaTeX

开发命令：

```powershell
cd frontend/web
npm install
npm run dev
npm run build
```

Vite 开发代理：

- `/api` -> `http://127.0.0.1:8000`
- `/diagnosis/api` -> `http://127.0.0.1:8000`

## 6. 前端文件职责

### 6.1 前端入口与配置

- `frontend/web/package.json`：前端依赖和脚本，包含 `dev`、`build`、`preview`。
- `frontend/web/package-lock.json`：npm 锁定依赖版本。
- `frontend/web/vite.config.ts`：Vite 配置、`@` 别名、开发代理和构建目录。
- `frontend/web/tsconfig.json`：TypeScript 编译配置。
- `frontend/web/index.html`：Vite HTML 入口。
- `frontend/web/src/main.ts`：创建 Vue App，挂载 Pinia、Router 和全局样式。
- `frontend/web/src/App.vue`：区分公共页面和登录后 AppShell；`/`、`/login`、`/register` 直接渲染页面，其余路由包在工作台壳里。
- `frontend/web/src/env.d.ts`：Vite/TypeScript 环境类型声明。
- `frontend/web/src/styles.css`：全局样式、工作台布局、通用卡片/按钮/表单/图表/响应式样式。

### 6.2 前端路由

- `frontend/web/src/router/index.ts`：定义公共宣传页、登录注册、工作台、诊断、画像、规划、资源、测评、历史、设置等路由，并设置页面标题。

### 6.3 前端 API 封装

- `frontend/web/src/api/client.ts`：Axios 实例、baseURL、20 秒超时、简单重试工具。
- `frontend/web/src/api/diagnosis.ts`：对接诊断 Agent API，包括学习者列表、画像、基础信息上传、诊断、自适应测试、复诊、成果检验。
- `frontend/web/src/api/planning.ts`：对接平台运行 API，包括创建课程规划 run、启动节点、完成节点、按 run_id 获取结果。
- `frontend/web/src/api/profile.ts`：画像适配 API，把诊断画像转换为后端规划使用的 canonical learner snapshot，并获取知识追踪评估。
- `frontend/web/src/api/assessment.ts`：提交测评、练习批改、刷新当前资源。
- `frontend/web/src/api/retrieval.ts`：证据检索搜索接口。
- `frontend/web/src/api/resources.ts`：从平台 run 中提取资源包。

### 6.4 前端类型

- `frontend/web/src/types/diagnosis.ts`：基础信息表单、自评领域、自适应测试会话等类型。
- `frontend/web/src/types/learner.ts`：学习者摘要、诊断画像、canonical learner snapshot、知识掌握、能力分、成果检验报告。
- `frontend/web/src/types/planning.ts`：课程路径节点、平台运行结果、规划状态、资源/检索/失败字段。
- `frontend/web/src/types/resource.ts`：讲义、案例、练习、测验等资源包类型。

### 6.5 前端状态管理

- `frontend/web/src/stores/learner.ts`：学习者全局状态；负责加载学习者、选择画像、适配规划 snapshot、保存基线、成果检验、本地持久化。
- `frontend/web/src/stores/diagnosis.ts`：学情诊断流程状态；管理基础表单、领域自评、项目经历、自适应测试会话、提交和恢复。
- `frontend/web/src/stores/learningPath.ts`：课程规划状态；管理平台 run、路径节点、当前节点、生成规划、启动/完成节点。

### 6.6 前端布局与导航

- `frontend/web/src/layouts/AppShell.vue`：登录后工作台壳；左侧导航、资源中心子菜单、顶部栏、用户入口、接口状态、RouterView。
- `frontend/web/src/components/layout/HomeNavbar.vue`：公共宣传页顶部导航外壳。
- `frontend/web/src/components/layout/DesktopNav.vue`：宣传页桌面端锚点导航。
- `frontend/web/src/components/layout/MobileMenu.vue`：宣传页移动端菜单。
- `frontend/web/src/components/layout/NavbarActions.vue`：宣传页登录、注册、开始使用和菜单按钮。
- `frontend/web/src/components/layout/BrandMark.vue`：品牌图标封装，读取 `brand-logo.png`。
- `frontend/web/src/components/layout/BrandWordmark.vue`：Logo + “织知成径”文字组合。
- `frontend/web/src/components/layout/LogoBrand.vue`：另一版 Logo 品牌链接组件。
- `frontend/web/src/composables/useHomeNavbar.ts`：宣传页导航状态、滚动监听、移动菜单开关、锚点跳转。

### 6.7 宣传页与视觉素材组件

- `frontend/web/src/views/LandingView.vue`：公共产品宣传首页；包含 Hero、产品价值、角色场景、工作流程、多智能体、知识库治理、个性化规划、CTA 和页脚。
- `frontend/web/src/components/landing/StoryShell.vue`：宣传页连续画卷外壳，承载全局氛围层和贯穿路径。
- `frontend/web/src/components/landing/GlobalAtmosphere.vue`：全局蓝白雾感、星点、低对比知识网络底纹。
- `frontend/web/src/components/landing/Artwork.vue`：可复用背景图层组件，绝对定位、渐隐遮罩、不参与正文布局。
- `frontend/web/src/assets/landing/hero-mountain-path.webp`：旧版首屏背景资源。
- `frontend/web/src/assets/landing/ambient-stars.svg`：旧版星点纹理。
- `frontend/web/public/assets/landing/*`：当前宣传页使用的 4K 背景资产，包括 hero、knowledge、learner、route、feedback、horizon、ambient-stars、story-path。

### 6.8 工作台页面

- `frontend/web/src/views/DashboardView.vue`：平台首页/工作台；展示平台智能进程、当前任务、Agent 状态、待办、最近活动、接口健康状态。
- `frontend/web/src/views/DiagnosisView.vue`：诊断入口页；展示诊断步骤、学习者选择、画像摘要和 AI 提示。
- `frontend/web/src/views/DiagnosisBasicView.vue`：基础信息页；录入姓名、教育背景、学习目标、领域基础、项目经历。
- `frontend/web/src/views/DiagnosisAssessmentView.vue`：自适应评估页；展示题目、选项、theta/覆盖率、答题和完成测试。
- `frontend/web/src/views/ProfileView.vue`：学习者画像页；展示掌握度、能力维度、知识点、学习成果检验、画像适配后的 planning snapshot。
- `frontend/web/src/views/LearningPathView.vue`：课程规划页；生成学习路径，选择当前节点，展示节点详情、状态和规划入口。
- `frontend/web/src/views/ResourcesView.vue`：资源中心；读取当前 run 的资源包，渲染讲义、示例、练习、测验，提交 quiz，刷新资源。
- `frontend/web/src/views/AssessmentView.vue`：测评反馈页；提交当前节点测评，驱动路径/掌握度更新。
- `frontend/web/src/views/HistoryView.vue`：学习历史页；当前为静态记录展示。
- `frontend/web/src/views/LoginView.vue`：登录页；当前为前端模拟提交。
- `frontend/web/src/views/RegisterView.vue`：注册页；当前为前端模拟提交。
- `frontend/web/src/views/SettingsView.vue`：个人设置页；通知、偏好、账号等轻量设置。

### 6.9 通用前端组件

- `frontend/web/src/components/ProgressRing.vue`：环形进度，用于掌握度/平台进程。
- `frontend/web/src/components/MasteryChart.vue`：ECharts 能力/掌握度柱状图。
- `frontend/web/src/components/ProfileSummary.vue`：学习者画像摘要卡。
- `frontend/web/src/components/DiagnosisStepper.vue`：诊断三步流程。
- `frontend/web/src/components/LearningPathMap.vue`：学习路径节点列表容器。
- `frontend/web/src/components/KnowledgeNode.vue`：单个路径知识节点按钮。
- `frontend/web/src/components/ResourceCard.vue`：资源类型卡片。
- `frontend/web/src/components/AICoachPanel.vue`：AI 辅助问答输入卡。
- `frontend/web/src/components/AIInsightCard.vue`：AI 洞察提示卡。
- `frontend/web/src/components/StateBlocks.vue`：空状态、加载、错误等状态块。
- `frontend/web/src/components/StatCard.vue`：统计卡片。
- `frontend/web/src/components/TaskCard.vue`：任务卡片。
- `frontend/web/src/components/illustrations/GuideFigure.vue`：SVG/CSS 生成的 AI 引导形象。
- `frontend/web/src/components/illustrations/MascotFigure.vue`：旧 mascot 图片展示。

## 7. 后端技术栈

位置：`src/skillforge_kb`

- Python 3.12
- FastAPI + Uvicorn
- Pydantic v2
- Typer CLI
- LangChain Core / LangGraph
- SQLite checkpoint/state
- PostgreSQL、Qdrant、Neo4j 预留与部分实现
- BM25 检索
- pytest、ruff、mypy

开发命令：

```powershell
uv sync --frozen
uv run pytest tests/unit -q
uv run ruff check src tests/unit
uv run mypy src/skillforge_kb
uv run skillforge-kb platform-serve --project-root . --host 127.0.0.1 --port 8000
```

## 8. 后端 API

主入口：`src/skillforge_kb/api/app.py`

- `GET /api/v1/health`：平台健康状态。
- `POST /api/v1/retrieval/search`：证据/知识检索。
- `POST /api/v1/profiles/adapt`：把诊断 Agent 输出转换为规划可用画像。
- `GET /api/v1/profiles/{profile_id}/knowledge-tracing/evaluation`：获取知识追踪评估。
- `POST /api/v1/runs`：创建或复用一次平台规划运行。
- `GET /api/v1/runs/{run_id}`：读取平台运行结果。
- `GET /api/v1/runs/{run_id}/events`：读取平台运行步骤记录。
- `POST /api/v1/runs/{run_id}/start-node`：开始某个课程节点。
- `POST /api/v1/runs/{run_id}/complete-node`：完成当前节点。
- `POST /api/v1/runs/{run_id}/assessment`：提交测评结果并更新路径。
- `POST /api/v1/runs/{run_id}/lecture-progress`：记录讲义学习进度。
- `POST /api/v1/runs/{run_id}/refresh-resources`：刷新当前节点资源。
- `POST /api/v1/runs/{run_id}/practice-review`：练习批改。
- `/diagnosis/*`：挂载独立学情诊断 Agent。
- `/assets`、`/static`、前端 fallback：生产环境托管 Vue 构建产物。

## 9. 后端文件职责

### 9.1 根包与配置

- `src/skillforge_kb/__init__.py`：Python 包标记。
- `src/skillforge_kb/config.py`：环境配置，包括 Postgres、Qdrant、Neo4j、LLM、超时、平台 SQLite 状态库。
- `src/skillforge_kb/cli.py`：命令行入口；启动平台服务、图谱验证/发布、融合 dry-run、规划评估、资源生成、模型检查等。
- `src/skillforge_kb/diagnosis_bridge.py`：把独立 `学情诊断Agent` 挂载到主 FastAPI 应用。

### 9.2 API 层

- `src/skillforge_kb/api/__init__.py`：导出 `create_app`。
- `src/skillforge_kb/api/app.py`：FastAPI 应用、HTTP 路由、异常处理、前端托管、诊断 Agent 挂载。

### 9.3 平台编排层

- `src/skillforge_kb/platform/__init__.py`：导出平台服务、模型、仓储和默认运行时。
- `src/skillforge_kb/platform/models.py`：平台请求/结果/阶段/状态/失败/学习进度等 Pydantic 模型。
- `src/skillforge_kb/platform/graph.py`：平台主流程编排；把画像、规划、检索、资源生成、反馈更新串成服务流程。
- `src/skillforge_kb/platform/runtime.py`：构建默认平台服务；加载 ontology、证据、检索语料、Agent、SQLite checkpoint。
- `src/skillforge_kb/platform/repository.py`：平台 run 的内存和 SQLite 持久化；处理幂等、评估观察记录、测评记录。
- `src/skillforge_kb/platform/ports.py`：平台依赖接口/端口定义。
- `src/skillforge_kb/platform/practice_review.py`：练习答案批改和反馈结果模型。

### 9.4 多智能体层

- `src/skillforge_kb/agents/__init__.py`：统一导出规划、检索、资源、反馈 Agent。
- `src/skillforge_kb/agents/planning_agent.py`：LangGraph 课程规划 Agent；处理事件路由、创建/更新路径、选择当前节点、检索当前节点知识。
- `src/skillforge_kb/agents/planning_agent_models.py`：规划 Agent 事件、状态、失败、下一步动作、结果模型。
- `src/skillforge_kb/agents/planning_tools.py`：LangChain-compatible 规划工具，封装 CoursePlanner 和 DepthUpdater。
- `src/skillforge_kb/agents/retrieval_agent.py`：领域检索 Agent；从正式证据和候选知识块中找当前节点证据。
- `src/skillforge_kb/agents/retrieval_agent_models.py`：检索请求、证据、证据缺口、检索结果模型。
- `src/skillforge_kb/agents/resource_agent.py`：资源生成 Agent；严格模式和候选预览模式，生成讲义、练习、测验、项目资源。
- `src/skillforge_kb/agents/resource_tools.py`：资源生成工具和 FakeResourceGenerator，负责输入校验和资源包验证。
- `src/skillforge_kb/agents/feedback.py`：规划反馈协调器；把测评事件转为画像更新和规划事件。
- `src/skillforge_kb/agents/assessment_feedback.py`：测评反馈 Agent；评估答题、生成掌握度变化和下一步深度建议。
- `src/skillforge_kb/agents/candidate_evidence_review.py`：候选证据审核队列与发布 manifest 生成。
- `src/skillforge_kb/agents/candidate_resource_pipeline.py`：候选资源生成演示流水线，从上游 handoff 生成个性化资源包和审计材料。
- `src/skillforge_kb/agents/runtime.py`：独立规划 Agent 运行时；加载事件、构建检索、执行单次事件。

### 9.5 课程规划核心

- `src/skillforge_kb/planning/__init__.py`：导出规划核心、适配、校准、评估工具。
- `src/skillforge_kb/planning/models.py`：路径节点、路径决策、策略、能力权重、状态和原因码。
- `src/skillforge_kb/planning/ordering.py`：根据课程图谱稳定生成必修概念顺序，校验先修顺序。
- `src/skillforge_kb/planning/planner.py`：CoursePlanner；根据画像、掌握度、先修关系决定学习/跳过/可用状态。
- `src/skillforge_kb/planning/updater.py`：DepthUpdater；在路径不重排的前提下更新节点深度和状态。
- `src/skillforge_kb/planning/adaptation.py`：节点权重与支持强度；计算 readiness、支持强度、资源配额基础信号。
- `src/skillforge_kb/planning/calibration.py`：节点权重策略的合成数据校准、敏感性分析、候选策略搜索。
- `src/skillforge_kb/planning/serialization.py`：路径 ID 和策略 digest 的稳定序列化。

### 9.6 知识图谱与课程本体

- `src/skillforge_kb/ontology/__init__.py`：导出 ontology 相关模型与加载工具。
- `src/skillforge_kb/ontology/models.py`：课程、章节、概念、关系、深度、学习者画像快照等核心模型。
- `src/skillforge_kb/ontology/catalog.py`：加载和查询课程目录、概念、章节、关系。
- `src/skillforge_kb/ontology/validation.py`：验证课程图谱完整性、DAG、先修关系、引用一致性。
- `src/skillforge_kb/ontology/neo4j.py`：把已审核课程图谱发布到 Neo4j。
- `src/skillforge_kb/ontology/coverage.py`：候选知识块对课程概念覆盖率分析。
- `src/skillforge_kb/ontology/concept_attributes.py`：概念能力要求、难度、权重等属性加载。
- `src/skillforge_kb/ontology/resource_blueprints.py`：资源蓝图加载与校验。
- `src/skillforge_kb/ontology/profile.py`：canonical learner profile 模型和画像结构。
- `src/skillforge_kb/ontology/profile_agent_adapter.py`：把外部学情诊断 Agent 输出适配成平台画像快照。

### 9.7 资料采集、清洗与融合

- `src/skillforge_kb/ingestion/__init__.py`：采集子包标记。
- `src/skillforge_kb/ingestion/fetch.py`：HTTP/本地源获取、超时、内容读取。
- `src/skillforge_kb/ingestion/loaders.py`：PDF/HTML/文本载入。
- `src/skillforge_kb/ingestion/normalize.py`：文本标准化、hash、去噪。
- `src/skillforge_kb/ingestion/chunking.py`：按教学语义切分为 evidence chunk。
- `src/skillforge_kb/fusion/__init__.py`：知识库融合子包标记。
- `src/skillforge_kb/fusion/inventory.py`：输入知识库文件清点。
- `src/skillforge_kb/fusion/jsonl.py`：JSONL 读写工具。
- `src/skillforge_kb/fusion/legacy.py`：旧知识库记录解析和归一化。
- `src/skillforge_kb/fusion/pilot.py`：pilot 知识块解析。
- `src/skillforge_kb/fusion/models.py`：融合候选、来源、摘要模型。
- `src/skillforge_kb/fusion/runner.py`：融合 dry-run 主流程。

### 9.8 检索与证据

- `src/skillforge_kb/retrieval/__init__.py`：导出检索模型、语料、BM25 和工具。
- `src/skillforge_kb/retrieval/models.py`：知识块、查询、命中、检索状态和检索结果。
- `src/skillforge_kb/retrieval/corpus.py`：加载一个或多个 JSONL 知识语料，构建 digest。
- `src/skillforge_kb/retrieval/bm25.py`：BM25 检索、tokenize、打分、anchor 加权。
- `src/skillforge_kb/retrieval/tool.py`：把检索器包装成 LangChain 工具。
- `src/skillforge_kb/evidence/__init__.py`：证据子包导出。
- `src/skillforge_kb/evidence/models.py`：证据记录、审核状态、证据类型。
- `src/skillforge_kb/evidence/manifest.py`：加载 evidence manifest，构建正式证据索引。
- `src/skillforge_kb/evidence/review_queue.py`：从候选证据生成审核队列。

### 9.9 资源生成

- `src/skillforge_kb/resources/__init__.py`：导出资源生成相关模型、brief、bundle、验证和演示工具。
- `src/skillforge_kb/resources/models.py`：ResourceBrief、生成门禁、证据过滤、引用要求、呈现偏好等模型。
- `src/skillforge_kb/resources/briefs.py`：ResourceBriefBuilder；从路径节点、画像、证据索引构造资源生成 brief/handoff。
- `src/skillforge_kb/resources/handoff.py`：ResourceHandoffContract；给下游资源 Agent 的不可变契约。
- `src/skillforge_kb/resources/evidence_bundle.py`：按 brief 组装 EvidenceBundle。
- `src/skillforge_kb/resources/generator_contracts.py`：讲义、实践指南、测评、项目资源和验证后的资源包模型。
- `src/skillforge_kb/resources/allocation.py`：按深度和支持强度分配时长、练习数、测验数、项目检查点。
- `src/skillforge_kb/resources/controlled_generation.py`：受控资源生成服务、LLM adapter、审计、引用验证、候选学习包。
- `src/skillforge_kb/resources/controlled_input.py`：把上游 profile/handoff/retrieval 转成资源生成 brief。
- `src/skillforge_kb/resources/controlled_evaluation.py`：多画像控制变量评估，比较个性化资源覆盖。
- `src/skillforge_kb/resources/demo_evidence.py`：冻结 CNN 官方文档证据，用于可审核演示。
- `src/skillforge_kb/resources/demo_export.py`：导出资源生成演示包、Markdown、Notebook、JSON 报告。
- `src/skillforge_kb/resources/notebook_runner.py`：运行固定 CNN notebook 验证代码示例。

### 9.10 学情评估与反馈

- `src/skillforge_kb/assessment/__init__.py`：导出 BKT 和规则式更新。
- `src/skillforge_kb/assessment/update.py`：规则式 answer event 更新，修改掌握度、置信度和错误模式。
- `src/skillforge_kb/assessment/bkt.py`：Bayesian Knowledge Tracing 基线模型和更新结果。
- `src/skillforge_kb/assessment/knowledge_tracing_experimental.py`：实验性知识追踪、观测、预测、评估逻辑。

### 9.11 评估、治理、绑定、存储

- `src/skillforge_kb/evaluation/__init__.py`：导出合成数据、路径评估、策略校准、知识追踪评估。
- `src/skillforge_kb/evaluation/models.py`：评估报告、指标、案例结果等模型。
- `src/skillforge_kb/evaluation/synthetic.py`：生成合成学习者/规划评估数据集。
- `src/skillforge_kb/evaluation/path_evaluation.py`：评估路径顺序、覆盖、跳过、深度等。
- `src/skillforge_kb/evaluation/planner_calibration.py`：规划策略搜索与校准报告。
- `src/skillforge_kb/evaluation/knowledge_tracing.py`：知识追踪预测观测评估。
- `src/skillforge_kb/governance/__init__.py`：治理包标记。
- `src/skillforge_kb/governance/policy.py`：证据发布、审核、许可证等治理策略。
- `src/skillforge_kb/governance/service.py`：治理服务封装。
- `src/skillforge_kb/binding/__init__.py`：候选资源绑定导出。
- `src/skillforge_kb/binding/models.py`：候选绑定模型。
- `src/skillforge_kb/binding/matcher.py`：把知识块/资源候选匹配到课程概念。
- `src/skillforge_kb/binding/report.py`：生成绑定覆盖报告。
- `src/skillforge_kb/storage/memory.py`：内存 SourceRepository。
- `src/skillforge_kb/storage/postgres.py`：PostgreSQL source/chunk repository 和 migration 执行。
- `src/skillforge_kb/storage/migrations/001_initial.sql`：Postgres 初始表结构。

### 9.12 旧领域 RAG/知识图谱流水线

位置：`src/skillforge_kb/domain/src`

- `data_collection.py`：采集课程资料和官方文档。
- `document_parser.py`：解析文档内容。
- `semantic_chunker.py`：语义切分。
- `build_markdown_index.py`：构建 Markdown 索引。
- `build_pipeline.py`：完整构建管道。
- `build_rag_only.py`：只构建 RAG 检索资产。
- `hybrid_retriever.py`：混合检索。
- `retrieval_agent.py`：旧版检索 Agent。
- `run_retrieval_agent.py`：运行旧版检索 Agent。
- `run_audited_retrieval.py`：运行带审核约束的检索。
- `kg_extraction.py`：从资料抽取知识图谱关系。
- `kg_schema_neo4j.py`：Neo4j 图谱 schema。
- `check_neo4j_connection.py`：检查 Neo4j 连接。
- `configs_loader.py`：加载 pipeline 配置。
- `evaluation.py`：旧流水线评估辅助。
- `domain/models.py`、`domain/enums.py`、`domain/ports.py`：领域基础模型、枚举和接口。

## 10. 独立学情诊断 Agent

位置：`学情诊断Agent`

- `main.py`：诊断 Agent FastAPI/核心入口。
- `models/schemas.py`：诊断请求、画像、答题、报告等 schema。
- `models/knowledge_graph.py`：诊断侧知识点图谱。
- `core/adaptive_test.py`：自适应测试流程。
- `core/irt.py`：IRT 能力估计。
- `core/mastery.py`：知识点掌握度计算。
- `core/gap_analyzer.py`：知识盲区分析。
- `core/profile_builder.py`：学习者画像构建。
- `core/retrieval.py`：诊断侧数据检索。
- `core/learning_verifier.py`：学习成果检验。
- `generators/mock_generator.py`：模拟题/数据生成。
- `data/*.json`：题库、知识点和 mock learners。
- `test_*.py`：诊断 Agent 的 API、流程、回归、安全、类型和端到端测试。

## 11. 脚本和资源

- `scripts/build_concept_resource_bindings.py`：构建概念到资源候选的绑定和报告。
- `scripts/build_cnn_evidence_review_queue.py`：生成 CNN 相关候选证据审核队列。
- `scripts/generate_graph_visualization.py`：生成课程知识图谱可视化 HTML/JSON。
- `resources/ontology/ai_course_v1.yaml`：AI 课程章节、概念、层级。
- `resources/ontology/ai_relations_v1.yaml`：概念关系和先修关系。
- `resources/ontology/concept_attributes_v1.yaml`：概念能力要求和属性。
- `resources/ontology/resource_blueprints_v1.yaml`：每个概念/深度需要的资源类型和时长蓝图。
- `resources/ontology/profile_agent_kp_map_v1.yaml`：诊断 Agent 知识点到平台概念的映射。
- `resources/ontology/legacy_profile_ids_v1.yaml`：旧画像 ID 映射。
- `resources/knowledge/cnn_convolution_candidates.jsonl`：CNN 卷积候选知识资源。
- `resources/evidence/evidence_manifest_v1.yaml`：正式证据 manifest。
- `data/index_chunks.jsonl`、`index_chunks.pkl`、`index_bm25.pkl`、`index_faiss.index`：本地检索索引/语料资产。
- `data/README.md`：数据使用、外部数据和许可说明。

## 12. 报告、示例和文档

- `examples/agents/initialize_event.json`：规划 Agent 初始化事件示例。
- `examples/simulations/profile-2026-0001-demo/*`：画像、规划结果、检索 Agent 输出、资源 Agent handoff、事件样例。
- `reports/resource_candidate_demo_20260811/*`：资源生成候选演示包，包括讲义、实践指南、测验、证据矩阵、审计报告、Notebook。
- `reports/controlled_generation_demo/generation_brief.json`：受控资源生成 brief 示例。
- `reports/2026-08-20-algorithm-ui-audit.md`：算法与 UI 审计说明。
- `docs/superpowers/specs/*`：各阶段设计规格，覆盖知识库、图谱、规划、评估、资源生成、BKT、平台集成。
- `docs/superpowers/plans/*`：对应实施计划和任务拆解。
- `docs/runbooks/*`：运行手册，说明课程规划 Agent、图谱可视化、概念资源绑定等操作。
- `docs/team/*`：团队协作、任务分配和算法协作说明。
- `docs/reports/*`：知识融合和课程图谱验证报告。

## 13. 测试结构

- `tests/unit/api/*`：FastAPI 和前端静态托管接口测试。
- `tests/unit/agents/*`：规划、检索、资源、反馈 Agent 单元测试。
- `tests/unit/planning/*`：CoursePlanner、路径顺序、更新、反馈、校准测试。
- `tests/unit/resources/*`：资源 brief、bundle、受控生成、Notebook、证据演示测试。
- `tests/unit/ontology/*`：课程本体、图谱、Neo4j、覆盖率、资源蓝图、画像适配测试。
- `tests/unit/retrieval/*`：BM25、语料、检索工具测试。
- `tests/unit/platform/*`：平台 runtime、repository、graph、completion policy 测试。
- `tests/unit/assessment/*`：规则更新和 BKT 测试。
- `tests/unit/evidence/*`：证据 manifest、模型、审核队列测试。
- `tests/unit/fusion/*`：融合 intake、legacy/pilot 解析、inventory 测试。
- `tests/unit/ingestion/*`：采集、加载、清洗、切分测试。
- `tests/unit/evaluation/*`：路径评估、合成数据、知识追踪、策略校准测试。
- `tests/unit/integration/*`：三 Agent 个性化资源流程的单元级集成测试。
- `tests/integration/*`：需要外部服务的集成测试。
- `tests/acceptance/*`：独立 Agent、资源 handoff、画像 API、检索输出、概念资源绑定等验收测试。

## 14. 数据流细节

1. 用户在前端 `/diagnosis/basic` 填基础信息。
2. 前端调用 `/diagnosis/api/learner/upload`，诊断 Agent 创建 learner。
3. 用户在 `/diagnosis/assessment` 做自适应测试。
4. 前端调用 `/diagnosis/api/adaptive-test/*`，诊断 Agent 更新 session。
5. 完成后调用诊断接口生成 `DiagnosisProfile`。
6. 前端 `learner.ts` 保存诊断画像到 localStorage。
7. 用户进入 `/learning-path` 生成课程规划。
8. 前端调用 `/api/v1/profiles/adapt` 把诊断画像转成 `LearnerSnapshot`。
9. 前端调用 `/api/v1/runs` 创建平台 run。
10. 后端平台服务加载 ontology、证据 manifest、知识语料。
11. CoursePlanningAgent/CoursePlanner 生成路径。
12. Retrieval Agent 找证据或候选证据。
13. ResourceBriefBuilder 构造资源生成契约。
14. ResourceGenerationAgent 生成资源或候选预览。
15. 前端 `/resources` 展示讲义、练习、测验和项目资源。
16. 用户提交测评或练习后，前端调用 `/assessment` 或 `/practice-review`。
17. 后端用规则/BKT 更新掌握度，保存 run 和观察记录。
18. 下一轮规划读取更新后的 profile/path，形成反馈闭环。

## 15. 设计时最重要的边界

- 公共宣传页不要展示真实用户数据，只讲产品价值、链路和角色。
- 工作台才展示平台进程、当前任务、接口状态、待处理事项和最近活动。
- 知识库属于资源中心；知识图谱更适合并入课程规划/路径展示。
- 平台的核心不是“生成内容”，而是“证据约束下的课程规划与反馈闭环”。
- 页面上不要把 Agent 画成工程架构图，应表达为“学习状态变化后，系统自动重新规划下一步”。
- 对外可以弱化内部 API、数据库、LangGraph 细节，强化“知识、学情、路径、资源、反馈”的连续故事。

