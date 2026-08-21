from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent, _is_relevant_chunk
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


def test_non_cnn_scope_does_not_accept_cnn_candidates(resource_case) -> None:
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
    assert result.candidate_evidence == ()
    assert result.evidence == ()
    assert result.evidence_gap is not None
    assert set(result.evidence_gap.missing_content_kinds) == set(
        handoff.evidence_filters.content_kinds
    )
    assert len({item.chunk_id for item in result.candidate_evidence}) == len(
        result.candidate_evidence
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


def test_retrieval_does_not_relabel_cnn_chunks_for_another_concept(resource_case) -> None:
    brief, _ = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)
    corpus = _corpus()
    agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        EvidenceIndex(version="evidence-manifest-v1", graph_version=handoff.graph_version),
    )
    request = DomainRetrievalRequest(
        original_query=f"{handoff.concept_id} intro",
        rewritten_queries=(f"{handoff.concept_id} definition",),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=3,
    )

    result = agent.retrieve(request, handoff)

    assert result.candidate_evidence == ()
    assert result.evidence_gap is not None


def test_declared_code_chunk_cannot_satisfy_exercise_query(resource_case) -> None:
    brief, _ = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)
    corpus = KnowledgeCorpus(
        chunks=(
            KnowledgeChunk(
                chunk_id="declared-code",
                doc_id="cnn-doc",
                source_title="CNN code",
                heading_path=("CNN", "Code"),
                text="Python PyTorch nn.Conv2d 输入输出 shape 参数。",
                domain_tag="ai-knowledge",
                difficulty="进阶",
                token_count=20,
                content_kind=ContentKind.CODE,
            ),
        ),
        digest="2" * 64,
    )
    agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        EvidenceIndex(version="evidence-manifest-v1", graph_version=handoff.graph_version),
    )
    request = DomainRetrievalRequest(
        original_query="卷积运算",
        rewritten_queries=("卷积输出尺寸练习",),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=3,
    )

    result = agent.retrieve(request, handoff)

    assert all(item.content_kind is not ContentKind.EXERCISE for item in result.candidate_evidence)


def test_retrieval_excludes_gan_and_transposed_convolution_content(resource_case) -> None:
    clean = KnowledgeChunk(
        chunk_id="cnn-clean",
        doc_id="cnn-doc",
        source_title="CNN convolution notes",
        heading_path=("CNN", "卷积运算"),
        text="标准卷积使用卷积核、padding、stride 和输出尺寸公式。",
        domain_tag="ai-knowledge",
        difficulty="进阶",
        token_count=20,
    )
    gan = KnowledgeChunk(
        chunk_id="cnn-gan",
        doc_id="gan-doc",
        source_title="DCGAN image generation guide",
        heading_path=("DCGAN", "转置卷积"),
        text="生成器使用 ConvTranspose2d 进行上采样，判别器使用卷积。",
        domain_tag="ai-knowledge",
        difficulty="进阶",
        token_count=20,
    )

    assert _is_relevant_chunk(clean, "dl.cnn.convolution")
    assert not _is_relevant_chunk(gan, "dl.cnn.convolution")


def test_metadata_fallback_produces_scoped_candidate_for_math_scalar(
    resource_case,
    catalog,
) -> None:
    brief, _ = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)
    empty_corpus = KnowledgeCorpus(chunks=(), digest="0" * 64)
    agent = DomainRetrievalAgent(
        empty_corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(empty_corpus)),
        EvidenceIndex(version="evidence-manifest-v1", graph_version=handoff.graph_version),
        catalog=catalog,
    )
    request = DomainRetrievalRequest(
        original_query=f"{handoff.concept_id} {handoff.delivery_depth.value}",
        rewritten_queries=(f"{handoff.concept_id} definition",),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=5,
    )

    result = agent.retrieve(request, handoff)

    metadata = [
        item
        for item in result.candidate_evidence
        if item.retrieval_method.value == "ontology_metadata"
    ]
    assert metadata
    assert all(item.concept_id == "math.linear-algebra.scalar" for item in metadata)
    assert all(item.evidence_status == "candidate" for item in metadata)
    assert all(item.license_status.value == "metadata_only" for item in metadata)
    assert any("标量" in item.excerpt for item in metadata)
    assert any(
        item.content_kind is ContentKind.CODE
        and "非执行代码" in item.excerpt
        for item in metadata
    )
    assert all("CNN" not in item.excerpt for item in metadata)


def test_non_cnn_retrieval_uses_concept_query_and_accepts_matching_chunk(
    resource_case,
    catalog,
) -> None:
    brief, _ = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)
    scalar = KnowledgeChunk(
        chunk_id="scalar-definition",
        doc_id="math-doc",
        source_title="线性代数基础",
        heading_path=("线性代数", "标量"),
        text="标量是只用一个数值表示大小的量。",
        domain_tag="math",
        difficulty="入门",
        token_count=20,
        content_kind=ContentKind.DEFINITION,
    )
    corpus = KnowledgeCorpus(chunks=(scalar,), digest="3" * 64)
    agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        EvidenceIndex(version="evidence-manifest-v1", graph_version=handoff.graph_version),
        catalog=catalog,
    )
    request = DomainRetrievalRequest(
        original_query="math.linear-algebra.scalar intro",
        rewritten_queries=("标量 定义", "标量 代码", "标量 练习"),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=5,
    )

    result = agent.retrieve(request, handoff)

    assert any(item.chunk_id == "scalar-definition" for item in result.candidate_evidence)


def test_non_cnn_retrieval_rejects_unrelated_concept_chunk() -> None:
    unrelated = KnowledgeChunk(
        chunk_id="vector-definition",
        doc_id="math-doc",
        source_title="线性代数基础",
        heading_path=("线性代数", "向量"),
        text="向量由多个有序数值组成，定义和练习。",
        domain_tag="math",
        difficulty="入门",
        token_count=20,
        content_kind=ContentKind.DEFINITION,
    )
    assert not _is_relevant_chunk(
        unrelated,
        "math.linear-algebra.scalar",
        concept_terms=("标量", "Scalar"),
    )
