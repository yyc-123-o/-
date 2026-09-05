"""Build a deterministic cross-check report between the primary and external corpora."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skillforge_kb.evidence.cross_check import build_cross_check_report, write_cross_check_report  # noqa: E402
from skillforge_kb.evidence.external_corpus import load_external_corpus  # noqa: E402
from skillforge_kb.ontology.catalog import OntologyCatalog  # noqa: E402
from skillforge_kb.retrieval.corpus import KnowledgeCorpus  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only cross-check report for the external knowledge corpus."
    )
    parser.add_argument(
        "--primary-file",
        type=Path,
        default=ROOT / "data" / "index_chunks.jsonl",
        help="Primary corpus JSONL file.",
    )
    parser.add_argument(
        "--external-file",
        type=Path,
        required=True,
        help="External corpus JSONL file used for verification only.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        required=True,
        help="Destination JSON report path.",
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
        "--core-concept-id",
        action="append",
        dest="core_concept_ids",
        help="Optional repeated scope filter; defaults to all known concepts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    primary_path = args.primary_file.expanduser().resolve()
    external_path = args.external_file.expanduser().resolve()
    output_path = args.output_file.expanduser().resolve()
    if output_path in {primary_path, external_path}:
        raise ValueError("output file must not overwrite an input corpus")

    catalog = OntologyCatalog.load(
        args.course_file.expanduser().resolve(),
        args.relations_file.expanduser().resolve(),
    )
    primary = KnowledgeCorpus.load(primary_path)
    external = load_external_corpus(external_path)
    report = build_cross_check_report(
        primary,
        external,
        catalog,
        core_concept_ids=tuple(args.core_concept_ids) if args.core_concept_ids else None,
    )
    write_cross_check_report(report, output_path)
    print(
        json.dumps(
            {
                "output_file": str(output_path),
                "summary": report["summary"],
                "gate_decision": report["gate_decision"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
