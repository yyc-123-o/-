# 资源生成 Agent：候选资源流水线

此入口消费一个输入文件夹中的三份上游 JSON：

- 名称包含“学情画像”的学情诊断结果；
- 名称包含“resource_agent_handoff”的课程规划交接；
- 名称包含“domain_retrieval_agent_output”的领域检索结果。

课程规划交接是概念、深度、先修与发布门禁的唯一权威；学情画像只影响讲解顺序、易错点和呈现偏好。这样不会因为画像希望“进阶”就覆盖课程规划的“入门补救”结论。

## 使用方式

在仓库根目录执行：

~~~powershell
$env:PYTHONPATH = "$PWD\src"
@'
from pathlib import Path
from skillforge_kb.agents.candidate_resource_pipeline import InputFolderResourceAgent

agent = InputFolderResourceAgent()
package = agent.build(
    "D:\你的输入文件夹",
    allow_candidate_drafts=True,  # 仅用于明确开启的展示草稿
)
agent.export(package, Path("reports") / "resource_candidate_demo")
print(package.release_status)
'@ | python -
~~~

默认 allow_candidate_drafts=False。当课程规划门禁未通过，或 definition、code、exercise 三类正式证据未全部发布时，资源不会生成。

开启候选草稿后，输出仍会带 candidate_draft 状态，且包含：

- 01_resource_decision_card.json：输入来源、个性化依据、阻塞与冲突；
- 02_evidence_matrix.json：每类资源引用了哪些候选/正式证据；
- 03_quality_report.json：发布门禁、缺失证据和下一步动作；
- lecture_notes.md、pytorch_practical_guide.md、layered_assessment.md；
- resource_package.json：整个资源包清单。

只有课程规划交接设置 allowed=true，并且三类证据同时满足 review_status=published、evidence_status=published 与许可证合规时，输出才会成为 published。

## 审核到发布的交接

候选证据先由 CandidateEvidenceReviewAgent 导出审核报告和审核填写模板。只有具备权限的审核人逐条确认后，才能生成 evidence_publication_manifest.json。

将该清单和三份上游输入放在同一输入目录后，资源生成入口会校验清单的 concept_id、depth、审核状态和许可证状态，并只升级清单中明确列出的证据。没有清单、清单范围不匹配、或三类证据不齐全时，资源状态仍会保持 candidate_draft 或 blocked。
