# 双路径个性化学习实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使用诊断证据生成完整路径与个性化路径，并允许学生主动学习被跳过节点。

**Architecture:** 在规划器中增加全量/个性化两次规划；画像快照保留可选的题目证据摘要，规划器使用可审计的掌握度判定。平台结果新增 `full_path`，默认资源链路继续使用 `path`。

**Tech Stack:** Python 3.12, Pydantic, FastAPI, pytest。

## Global Constraints

- 资源生成 Agent 继续消费个性化 `planning.path`。
- 不删除已有路径字段和已有事件契约。
- 跳过判定必须要求题目证据数量、掌握度和置信度同时达标。

### Task 1: 扩展画像证据模型

**Files:**
- Modify: `src/skillforge_kb/ontology/models.py`
- Modify: `src/skillforge_kb/ontology/profile_agent_adapter.py`
- Test: `tests/unit/ontology/test_profile_agent_adapter.py`

- [ ] 增加可选的题目证据摘要模型，保存 `concept_id`、正确与总题数、稳定性、错误标记和最近时间。
- [ ] 适配器读取画像中的可选诊断证据；缺失时保持空集合并兼容旧画像。
- [ ] 为有效、缺失和未知知识点证据添加测试。

### Task 2: 实现证据推断和双路径规划

**Files:**
- Modify: `src/skillforge_kb/planning/models.py`
- Modify: `src/skillforge_kb/planning/planner.py`
- Test: `tests/unit/planning/test_planner.py`

- [ ] 增加 `full_path` 结果字段和节点掌握证据元数据。
- [ ] 实现直接掌握度、题目正确率、稳定性、时效性和错误惩罚的确定性聚合。
- [ ] 仅在三项跳过门槛同时满足时将节点标记为 `SKIPPED`。
- [ ] 验证标量高掌握度时个性化路径跳过、完整路径保留该节点；无题目证据时不跳过。

### Task 3: 接入规划 Agent 和平台结果

**Files:**
- Modify: `src/skillforge_kb/agents/planning_agent_models.py`
- Modify: `src/skillforge_kb/agents/planning_agent.py`
- Modify: `src/skillforge_kb/platform/models.py`
- Modify: `src/skillforge_kb/platform/graph.py`
- Test: `tests/unit/platform/test_graph.py`

- [ ] 在规划结果中返回 `full_path`，保持 `path` 为个性化路径。
- [ ] 初始化和画像刷新时同时生成两条路径。
- [ ] 验证平台结果身份字段与两条路径一致。

### Task 4: 支持完整路径主动启动

**Files:**
- Modify: `src/skillforge_kb/platform/graph.py`
- Modify: `src/skillforge_kb/api/app.py`
- Test: `tests/unit/api/test_app.py`

- [ ] 扩展启动节点请求，支持 `path_mode=full`。
- [ ] 对被跳过节点校验硬前置，满足时允许生成资源。
- [ ] 保持默认启动行为和现有错误码兼容。

### Task 5: 全量验证

- [ ] 运行规划、画像适配和平台测试。
- [ ] 运行 `pytest -q`。
- [ ] 运行 `git diff --check`。
