import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skillforge_kb.binding.matcher import build_candidate_bindings
from skillforge_kb.binding.report import build_binding_report, write_binding_outputs
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build candidate knowledge-chunk bindings for the course graph."
    )
    parser.add_argument(
        "--course-file",
        type=Path,
        default=ROOT / "resources" / "ontology" / "ai_course_v1.yaml",
    )
    parser.add_argument(
        "--relations-file",
        type=Path,
        default=ROOT / "resources" / "ontology" / "ai_relations_v1.yaml",
    )
    parser.add_argument(
        "--knowledge-file",
        type=Path,
        default=ROOT / "data" / "index_chunks.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "generated" / "concept-resource-bindings",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = OntologyCatalog.load(args.course_file, args.relations_file)
    corpus = KnowledgeCorpus.load(args.knowledge_file)
    bindings = build_candidate_bindings(catalog, corpus)
    report = build_binding_report(catalog, corpus, bindings)
    write_binding_outputs(args.output_dir, bindings, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
