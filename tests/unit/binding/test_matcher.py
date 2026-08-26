import json
from pathlib import Path

from skillforge_kb.binding.matcher import build_candidate_bindings
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

RESOURCE_ROOT = Path(__file__).parents[3] / "resources" / "ontology"


def catalog() -> OntologyCatalog:
    return OntologyCatalog.load(
        RESOURCE_ROOT / "ai_course_v1.yaml",
        RESOURCE_ROOT / "ai_relations_v1.yaml",
    )


def chunk(
    chunk_id: str,
    *,
    source_title: str,
    heading_path: list[str],
    text: str,
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": f"doc-{chunk_id}",
        "source_title": source_title,
        "heading_path": heading_path,
        "text": text,
        "page_no": None,
        "domain_tag": "ai-knowledge",
        "difficulty": "进阶",
        "token_count": len(text),
    }


def corpus(tmp_path: Path, rows: list[dict[str, object]]) -> KnowledgeCorpus:
    path = tmp_path / "chunks.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return KnowledgeCorpus.load(path)


def test_exact_title_and_body_matches_include_curriculum_location(tmp_path: Path) -> None:
    result = build_candidate_bindings(
        catalog(),
        corpus(
            tmp_path,
            [
                chunk(
                    "rag-title",
                    source_title="RAG 检索增强生成",
                    heading_path=["检索增强生成"],
                    text="本节介绍 RAG 的基本流程。",
                ),
                chunk(
                    "lora-body",
                    source_title="模型训练实践",
                    heading_path=["方法"],
                    text="低秩适配微调通过低秩矩阵减少训练参数。",
                ),
            ],
        ),
    )

    assert [(item.chunk_id, item.concept_id) for item in result] == [
        ("lora-body", "llm.finetuning.lora"),
        ("rag-title", "rag.retrieval-augmented-generation"),
    ]
    title_binding = next(item for item in result if item.chunk_id == "rag-title")
    assert title_binding.match_type == "title_exact_name"
    assert title_binding.section_id == "section.10.generation-diagnostics"
    assert title_binding.chapter_id == "chapter.10.rag"
    assert title_binding.review_status == "candidate"
    assert title_binding.evidence_state == "candidate"


def test_partial_title_matches_are_stable_and_deduplicated(tmp_path: Path) -> None:
    rows = [
        chunk(
            "cnn",
            source_title="视觉模型",
            heading_path=["卷积神经网络"],
            text="卷积神经网络（CNN）能够提取局部特征。",
        ),
        chunk(
            "noise",
            source_title="普通文章",
            heading_path=[],
            text="没有课程概念名称的片段。",
        ),
    ]
    first = build_candidate_bindings(catalog(), corpus(tmp_path, rows))
    second = build_candidate_bindings(catalog(), corpus(tmp_path, rows))

    assert first == second
    assert [item.chunk_id for item in first] == ["cnn"]
    assert first[0].concept_id == "dl.cnn.architecture"
    assert first[0].match_type == "title_partial_name"
    assert 0 < first[0].score < 1
