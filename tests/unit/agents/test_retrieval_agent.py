from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent
from skillforge_kb.agents.retrieval_agent_models import DomainRetrievalRequest
from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.models import KnowledgeChunk
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool


def _corpus() -> KnowledgeCorpus:
    rows = (
        KnowledgeChunk(
            chunk_id="cnn-definition",
            doc_id="cnn-doc",
            source_title="dl.cnn.convolution CNN",
            heading_path=("CNN", "定义"),
            text="卷积运算使用局部卷积核，padding stride 输出尺寸。卷积 CNN。",
            domain_tag="ai-knowledge",
            difficulty="进阶",
            token_count=30,
        ),
        KnowledgeChunk(
            chunk_id="cnn-code",
            doc_id="cnn-doc",
            source_title="dl.cnn.convolution CNN",
            heading_path=("CNN", "PyTorch 代码"),
            text="Python PyTorch nn.Conv2d 输入输出 shape 参数。卷积 CNN。",
            domain_tag="ai-knowledge",
            difficulty="进阶",
            token_count=30,
        ),
        KnowledgeChunk(
            chunk_id="cnn-exercise",
            doc_id="cnn-doc",
            source_title="dl.cnn.convolution CNN",
            heading_path=("CNN", "练习"),
            text="卷积输出尺寸计算、卷积核参数量、padding stride 练习答案解析。CNN。",
            domain_tag="ai-knowledge",
            difficulty="进阶",
            token_count=30,
        ),
    )
    return KnowledgeCorpus(chunks=rows, digest="1" * 64)


def test_agent_queries_definition_code_and_exercise(resource_case) -> None:
    brief, _ = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)
    corpus = _corpus()
    agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        EvidenceIndex(version="evidence-manifest-v1", graph_version=handoff.graph_version),
    )
    request = DomainRetrievalRequest(
        original_query=f"{handoff.concept_id} {handoff.delivery_depth.value}",
        rewritten_queries=("卷积运算 CNN", "PyTorch nn.Conv2d", "输出尺寸练习"),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=DepthLevel(handoff.delivery_depth),
        top_k=3,
    )

    result = agent.retrieve(request, handoff)

    assert set(result.request.rewritten_queries) == {
        "卷积运算 CNN",
        "PyTorch nn.Conv2d",
        "输出尺寸练习",
    }
    assert {item.content_kind for item in result.candidate_evidence} == set(
        handoff.evidence_filters.content_kinds
    )
    assert result.evidence == ()
    assert result.evidence_gap is not None
    assert set(result.evidence_gap.missing_content_kinds) == set(
        handoff.evidence_filters.content_kinds
    )


def test_candidate_hits_remain_unapproved(resource_case) -> None:
    brief, _ = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)
    corpus = _corpus()
    agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        EvidenceIndex(version="evidence-manifest-v1", graph_version=handoff.graph_version),
    )
    request = DomainRetrievalRequest(
        original_query="卷积运算",
        rewritten_queries=("卷积运算 CNN",),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=3,
    )

    result = agent.retrieve(request, handoff)

    assert all(item.evidence_status == "candidate" for item in result.candidate_evidence)
    assert all(item.content_kind in {
        ContentKind.DEFINITION,
        ContentKind.CODE,
        ContentKind.EXERCISE,
    } for item in result.candidate_evidence)
