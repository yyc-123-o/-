# Evidence Governance Design

## Goal

将现有人工智能领域候选语料整理为可审计的证据审核队列，并为审核通过后的正式 `EvidenceRecord` 发布提供完整元数据与覆盖统计；未经人工审核的内容不得自动进入正式证据清单。

## Scope

- 首批治理范围为当前 AI 课程图谱中的核心知识点子集，默认由输入参数指定。
- 输入为带来源元数据、概念 ID 和内容类型的 JSONL 候选语料。
- 输出为候选审核队列和按知识点/内容类型统计的覆盖报告。
- 不自动判断专业正确性，不自动授予版权许可，不自动写入正式证据清单。
- 保留 `build_cnn_review_queue` 作为兼容包装，但底层使用通用治理规则。

## Data Flow

```text
candidate JSONL
  -> schema and metadata validation
  -> exact concept binding against OntologyCatalog
  -> source/license/content-kind checks
  -> proposed depth and locator normalization
  -> candidate review queue (publishable=false)
  -> human review and adjudication outside this command
  -> explicit EvidenceRecord generation in a later publish step
```

## Governance Rules

1. `concept_ids` 必须是列表，且每个 ID 必须存在于当前图谱；未知 ID 进入排除清单，不做猜测映射。
2. 每条候选必须有 `chunk_id`、`source_id`、`source_title`、`source_url`、`license_status`、`language`、`content_kind`、`locator`、`text` 和 64 位内容哈希。
3. 只有 `license_status=allowed` 的候选进入人工审核队列；其他状态保留排除原因。
4. `content_kind` 使用项目枚举，首批覆盖统计要求 `definition`、`code`、`exercise`。
5. 候选记录固定为 `review_status=candidate`、`publishable=false`；工具不写 `published`。
6. `depth` 只在输入明确提供时采用；否则由 `difficulty` 生成 `proposed_depth`，并标记为推断值，不能直接用于正式发布。
7. 覆盖率分母由调用方传入的核心知识点清单决定，不使用已召回候选数作为分母。

## Output Contract

输出 `evidence-review-queue.v1`，包含：

- `graph_version`、`core_concept_ids`、`candidate_count`、`excluded_count`；
- 每条候选的标准化来源、许可、概念、深度、内容类型、定位、哈希和审核状态；
- 每条排除记录的 `chunk_id` 和确定性 `reason`；
- 每个核心知识点的 `available_content_kinds`、`missing_content_kinds`、候选数量和 `ready_for_human_review`；
- `coverage_summary`，包含知识点覆盖率和三类资源完整率。

## Safety and Review Boundary

候选队列不是正式证据。人工审核者必须独立确认专业正确性、来源可追溯性和许可证适用范围，再由后续发布命令构造符合 `EvidenceRecord` 校验的记录。书籍 PDF、第三方整理材料和无法确认授权的内容默认保持候选状态。

## Verification

- 单元测试覆盖未知概念、缺元数据、非法许可、重复 chunk、缺失内容类型、深度推断和核心覆盖统计。
- 使用现有 `ai_learning_pilot_review_300.jsonl` 生成一次只读队列，检查输出不覆盖输入。
- 运行全量单元测试和 `ruff check`，不改变运行时正式证据门禁。
