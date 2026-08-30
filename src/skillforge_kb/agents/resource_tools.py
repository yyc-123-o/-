from typing import TypedDict

from pydantic import TypeAdapter

from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceType
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.resources.briefs import RESOURCE_EVIDENCE_KINDS
from skillforge_kb.resources.evidence_bundle import EvidenceBundle
from skillforge_kb.resources.generator_contracts import (
    AssessmentResource,
    CitationRecord,
    EvidenceBoundItem,
    GeneratedArtifact,
    LectureResource,
    PracticalGuideResource,
    ProjectResource,
    ResourceGenerator,
    ValidatedResourcePackage,
    build_resource_result_id,
)
from skillforge_kb.resources.models import ResourceBrief


class _ArtifactFields(TypedDict):
    path_id: str
    graph_version: str
    concept_id: str
    delivery_depth: DepthLevel
    sequence: int
    hard_prerequisite_ids: tuple[str, ...]
    covered_learning_outcomes: tuple[str, ...]
    items: tuple[EvidenceBoundItem, ...]


_ARTIFACTS_ADAPTER = TypeAdapter(tuple[GeneratedArtifact, ...])


class FakeResourceGenerator:
    def generate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
    ) -> tuple[GeneratedArtifact, ...]:
        artifacts: list[GeneratedArtifact] = []
        for resource_type in brief.required_resource_types:
            citations = tuple(
                CitationRecord(
                    evidence_id=record.evidence_id,
                    source_id=record.source_id,
                    chunk_id=record.chunk_id,
                    locator=record.locator,
                    normalized_hash=record.normalized_hash,
                )
                for record in bundle.records
                if record.content_kind in RESOURCE_EVIDENCE_KINDS[resource_type]
            )
            common: _ArtifactFields = {
                "path_id": brief.path_id,
                "graph_version": brief.graph_version,
                "concept_id": brief.concept_id,
                "delivery_depth": brief.delivery_depth,
                "sequence": brief.sequence,
                "hard_prerequisite_ids": brief.hard_prerequisite_ids,
                "covered_learning_outcomes": brief.learning_outcomes,
                "items": tuple(
                    EvidenceBoundItem(text=text, citations=citations)
                    for text in _resource_items(resource_type, brief)
                ),
            }
            if resource_type is ResourceType.LECTURE:
                artifacts.append(
                    LectureResource(
                        **common,
                        resource_type=ResourceType.LECTURE,
                    )
                )
            elif resource_type is ResourceType.PRACTICAL_GUIDE:
                artifacts.append(
                    PracticalGuideResource(
                        **common,
                        resource_type=ResourceType.PRACTICAL_GUIDE,
                    )
                )
            elif resource_type is ResourceType.ASSESSMENT:
                artifacts.append(
                    AssessmentResource(
                        **common,
                        resource_type=ResourceType.ASSESSMENT,
                        assessment_kinds=brief.assessment_kinds,
                    )
                )
            else:
                artifacts.append(
                    ProjectResource(
                        **common,
                        resource_type=ResourceType.PROJECT,
                    )
                )
        return tuple(artifacts)


_TOPIC_LABELS = {
    "convolution": "卷积运算",
    "cross-correlation": "互相关",
    "matrix": "矩阵",
    "matrix-multiplication": "矩阵乘法",
    "tensor": "张量",
    "vector": "向量",
}


def _resource_items(resource_type: ResourceType, brief: ResourceBrief) -> tuple[str, ...]:
    """Create evidence-bound, learner-facing content for the formal package."""
    topic_slug = brief.concept_id.rsplit(".", 1)[-1]
    topic = _TOPIC_LABELS.get(topic_slug, topic_slug.replace("-", " "))
    outcome = brief.learning_outcomes[0]
    if resource_type is ResourceType.LECTURE:
        return (
            f"学习目标：{outcome}。本节围绕“{topic}”建立从输入、变换到输出的完整解释链。",
            f"核心定义：先明确“{topic}”接收的输入表示、允许的操作和输出含义；任何公式都必须同时满足这些边界条件。",
            f"推导与示例：选择最小数值例子，逐步写出中间量，再用代码打印输入、关键参数和结果，核对手算与实现是否一致。",
            f"边界与辨析：比较一个相邻概念或参数变化，说明结果为什么不同；重点检查形状、顺序、步长和边界处理。",
            f"迁移任务：把“{topic}”放入一个稍有变化的应用场景，解释它仍然如何支持学习目标“{outcome}”。",
        )
    if resource_type is ResourceType.PRACTICAL_GUIDE:
        return (
            f"实验问题：{topic} 的哪个输入或参数决定输出变化？先写下可证伪的预测，再开始运行。",
            "基线实验：固定输入和默认参数，记录输入形状、关键中间值、输出形状与运行结果。",
            "单变量实验：一次只改变一个参数，至少完成三组对照，并把预测、实际输出和差异原因放入表格。",
            "边界实验：测试全零、最小尺寸或不满足约束的输入，记录程序输出或报错信息并解释其来源。",
            "复现与结论：保留环境、参数和随机种子；用三句话总结规律、适用边界以及对学习目标的支撑。",
        )
    if resource_type is ResourceType.ASSESSMENT:
        return (
            f"概念检查：用自己的话定义“{topic}”，指出输入、核心规则和输出。",
            f"计算检查：为“{topic}”构造一个最小数值例子，写出每一步中间量并核对最终结果。",
            f"形状推理：修改一个关键参数，重新推导输出形状，说明变化是由哪条规则导致的。",
            f"代码调试：阅读一段“{topic}”实现，定位一个形状、参数顺序或边界处理错误并给出修复理由。",
            f"综合迁移：说明“{topic}”与前置知识的关系，并给出一个适用与一个不适用的场景。",
        )
    return (
        f"项目目标：将“{topic}”应用到一个最小可验证任务，并明确验收标准：{outcome}。",
        "交付物一：提交可复现代码、依赖版本、输入样例和关键参数表。",
        "交付物二：提交结果截图或日志，解释输出形状、指标变化和一次失败尝试。",
        "评审要点：检查实现是否满足输入约束、是否保留中间结果、是否能由他人复现。",
        "复盘要求：说明一个可继续优化的方向，以及该方向可能引入的风险或权衡。",
    )


class ResourceGenerationTool:
    def invoke(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
        generator: ResourceGenerator,
    ) -> ValidatedResourcePackage:
        validated_brief, validated_bundle = self._validate_inputs(brief, bundle)
        if not validated_brief.generation_gate.allowed:
            raise ValueError("generation gate does not allow formal resource generation")
        if validated_brief.status is PathStatus.BLOCKED:
            raise ValueError("blocked resource briefs cannot enter formal generation")
        return self.validate(
            validated_brief,
            validated_bundle,
            generator.generate(validated_brief, validated_bundle),
        )

    def validate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
        artifacts: tuple[GeneratedArtifact, ...],
    ) -> ValidatedResourcePackage:
        brief, bundle = self._validate_inputs(brief, bundle)
        if not brief.generation_gate.allowed:
            raise ValueError("generation gate does not allow formal resource generation")
        if brief.status is PathStatus.BLOCKED:
            raise ValueError("blocked resource briefs cannot enter formal generation")
        artifacts = _ARTIFACTS_ADAPTER.validate_python(artifacts)
        if bundle.brief_id != brief.brief_id:
            raise ValueError("evidence bundle does not match resource brief")
        if (
            bundle.graph_version != brief.graph_version
            or bundle.concept_id != brief.concept_id
            or bundle.depth is not brief.delivery_depth
        ):
            raise ValueError("evidence bundle scope does not match resource brief")
        actual_types = [artifact.resource_type for artifact in artifacts]
        if len(actual_types) != len(set(actual_types)) or set(actual_types) != set(
            brief.required_resource_types
        ):
            raise ValueError("generated artifacts do not match required resource types")

        evidence_by_id = {record.evidence_id: record for record in bundle.records}
        allowed_evidence_ids = set(evidence_by_id)
        for artifact in artifacts:
            if (
                artifact.path_id != brief.path_id
                or artifact.graph_version != brief.graph_version
                or artifact.concept_id != brief.concept_id
                or artifact.delivery_depth is not brief.delivery_depth
                or artifact.sequence != brief.sequence
                or artifact.hard_prerequisite_ids != brief.hard_prerequisite_ids
            ):
                raise ValueError("generated artifact changed the path contract")
            if artifact.covered_learning_outcomes != brief.learning_outcomes:
                raise ValueError("generated artifact does not cover learning outcomes")
            if not artifact.items:
                raise ValueError("generated artifact requires evidence-bound items")
            cited_kinds = set()
            for item in artifact.items:
                if not item.citations:
                    raise ValueError("generated item requires a citation")
                unknown = set(item.evidence_ids) - allowed_evidence_ids
                if unknown:
                    raise ValueError("generated item cites unknown evidence")
                allowed_kinds = set(RESOURCE_EVIDENCE_KINDS[artifact.resource_type])
                for citation in item.citations:
                    record = evidence_by_id[citation.evidence_id]
                    if (
                        citation.source_id != record.source_id
                        or citation.chunk_id != record.chunk_id
                        or citation.locator != record.locator
                        or citation.normalized_hash != record.normalized_hash
                    ):
                        raise ValueError("generated citation metadata does not match evidence")
                    if record.content_kind not in allowed_kinds:
                        raise ValueError(
                            "generated item cites the wrong resource evidence kind"
                        )
                    cited_kinds.add(record.content_kind)
            if not allowed_kinds.issubset(cited_kinds):
                raise ValueError(
                    "generated artifact does not cite all required evidence kinds"
                )
            if isinstance(artifact, AssessmentResource) and (
                artifact.assessment_kinds != brief.assessment_kinds
            ):
                raise ValueError("assessment kinds do not match resource brief")

        ordered = tuple(
            sorted(artifacts, key=lambda artifact: artifact.resource_type.value)
        )
        payload = {
            "artifacts": [artifact.model_dump(mode="json") for artifact in ordered],
            "brief_id": brief.brief_id,
            "bundle_id": bundle.bundle_id,
        }
        return ValidatedResourcePackage(
            result_id=build_resource_result_id(payload),
            brief_id=brief.brief_id,
            bundle_id=bundle.bundle_id,
            artifacts=ordered,
        )

    @staticmethod
    def _validate_inputs(
        brief: ResourceBrief,
        bundle: EvidenceBundle,
    ) -> tuple[ResourceBrief, EvidenceBundle]:
        return (
            ResourceBrief.model_validate(brief.model_dump()),
            EvidenceBundle.model_validate(bundle.model_dump()),
        )
