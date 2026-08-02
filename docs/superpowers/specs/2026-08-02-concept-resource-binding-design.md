# Concept Resource Binding Design

## Goal

将队友知识库中的候选片段作为课程知识图谱的“教学资源证据层”接入，生成可审核的“知识片段 -> 课程概念”候选绑定，同时保持课程章节、概念和先修关系不变。

## Scope

- 输入课程本体 `resources/ontology/ai_course_v1.yaml`、队友知识库 `data/index_chunks.jsonl`。
- 使用概念中文名、英文名、别名和标题路径进行确定性匹配。
- 输出每条候选绑定的概念、片段、匹配分数、匹配依据、审核状态和来源信息。
- 默认状态为 `candidate`，不写入正式证据清单，不创建正式先修关系。
- 输出覆盖率、每概念命中数和未覆盖概念报告，供人工审核。

## Architecture

新增独立绑定模块和 CLI 脚本。绑定模块加载既有 `OntologyCatalog` 与 `KnowledgeCorpus`，对每个片段构造搜索文本；精确匹配概念正式名称或别名时生成候选边，并按匹配位置、名称类型和文本长度计算稳定分数。报告生成器只消费候选边，不改变核心本体。

候选边使用 JSONL 存储，字段包括 `binding_id`、`chunk_id`、`concept_id`、`section_id`、`chapter_id`、`match_type`、`score`、`review_status` 和 `evidence_state`。正式发布仍需来源、许可证、概念绑定和人工审核完整。

## Validation

- 单元测试覆盖名称匹配、别名匹配、标题优先级、重复绑定去重、无匹配片段和稳定排序。
- 集成测试使用仓库实际本体与候选知识库，验证输出可重建、所有概念 ID 合法、所有边为 `candidate`，且不产生正式证据边。
- 运行脚本后生成 JSONL 和 JSON 报告，记录输入摘要与输出摘要。
