import json
import subprocess
import sys
from pathlib import Path

from skillforge_kb.binding.matcher import build_candidate_bindings
from skillforge_kb.binding.report import build_binding_report, write_binding_outputs
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

ROOT = Path(__file__).parents[2]


def test_real_candidate_corpus_builds_auditable_graph_bindings(tmp_path: Path) -> None:
    catalog = OntologyCatalog.load(
        ROOT / "resources" / "ontology" / "ai_course_v1.yaml",
        ROOT / "resources" / "ontology" / "ai_relations_v1.yaml",
    )
    corpus = KnowledgeCorpus.load(ROOT / "data" / "index_chunks.jsonl")

    bindings = build_candidate_bindings(catalog, corpus)
    report = build_binding_report(catalog, corpus, bindings)
    write_binding_outputs(tmp_path, bindings, report)

    concept_ids = {concept.id for concept in catalog.concepts()}
    assert len(corpus.chunks) == 710
    assert bindings
    assert all(binding.concept_id in concept_ids for binding in bindings)
    assert all(binding.review_status == "candidate" for binding in bindings)
    assert all(binding.evidence_state == "candidate" for binding in bindings)
    assert report["publishable"] is False
    assert report["candidate_binding_count"] == len(bindings)
    assert report["input_chunk_count"] == 710

    jsonl_path = tmp_path / "concept_resource_candidates.jsonl"
    report_path = tmp_path / "concept_resource_binding_report.json"
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    written_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(rows) == len(bindings)
    assert written_report == report
    assert rows == sorted(rows, key=lambda row: (row["chunk_id"], row["concept_id"]))


def test_binding_cli_writes_candidate_outputs(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_concept_resource_bindings.py"),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["publishable"] is False
    assert summary["candidate_binding_count"] > 0
    assert (tmp_path / "concept_resource_candidates.jsonl").is_file()
    assert (tmp_path / "concept_resource_binding_report.json").is_file()
