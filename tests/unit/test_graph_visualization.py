import importlib.util
from pathlib import Path

from skillforge_kb.binding.matcher import build_candidate_bindings
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "generate_graph_visualization",
    ROOT / "scripts" / "generate_graph_visualization.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
graph_payload = _MODULE.graph_payload
render_html = _MODULE.render_html


def test_graph_payload_contains_candidate_resource_layer() -> None:
    catalog = OntologyCatalog.load(
        ROOT / "resources" / "ontology" / "ai_course_v1.yaml",
        ROOT / "resources" / "ontology" / "ai_relations_v1.yaml",
    )
    corpus = KnowledgeCorpus.load(ROOT / "data" / "index_chunks.jsonl")
    bindings = [
        binding.model_dump(mode="json")
        for binding in build_candidate_bindings(catalog, corpus)
    ]

    payload = graph_payload(catalog, bindings)

    assert payload["resourceBindings"] == bindings
    assert payload["logic"]["candidateBindingCount"] == len(bindings)
    assert payload["logic"]["boundConceptCount"] == 64
    vector = next(
        concept
        for concept in payload["concepts"]
        if concept["id"] == "math.linear-algebra.vector"
    )
    assert vector["resourceCount"] == 86


def test_render_html_escapes_candidate_source_titles() -> None:
    payload = {
        "version": "ai-course-v1",
        "chapters": [],
        "sections": [],
        "concepts": [],
        "edges": [],
        "resourceBindings": [
            {
                "concept_id": "safe.concept",
                "source_title": "</script><img src=x onerror=alert(1)>",
                "match_type": "body_exact_name",
            }
        ],
        "logic": {
            "conceptCount": 0,
            "hardPrerequisiteCount": 0,
            "crossChapterPrerequisites": [],
            "cycles": [],
            "reverseOrderEdges": [],
            "roots": [],
            "leaves": [],
            "isolatedConcepts": [],
            "candidateBindingCount": 1,
            "boundConceptCount": 1,
        },
    }

    html = render_html(payload)

    assert "</script><img" not in html
    assert "\\u003c/script\\u003e" in html
    assert "escapeHtml(resource.source_title)" in html
