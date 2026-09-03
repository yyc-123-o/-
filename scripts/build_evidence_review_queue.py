"""Build a candidate-only evidence governance queue from rich JSONL rows."""

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skillforge_kb.evidence.governance import build_review_queue  # noqa: E402
from skillforge_kb.ontology.catalog import OntologyCatalog  # noqa: E402


def _read_rows(path: Path) -> Iterator[dict[str, Any]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row {line_number} must be an object")
        yield row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a candidate-only evidence review queue."
    )
    parser.add_argument("--input-file", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
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
        help="Repeat for each core concept. Defaults to all graph concepts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input_file.expanduser().resolve()
    output_path = args.output_file.expanduser().resolve()
    if input_path == output_path:
        raise ValueError("output file must not overwrite input file")
    catalog = OntologyCatalog.load(
        args.course_file.expanduser().resolve(),
        args.relations_file.expanduser().resolve(),
    )
    payload = build_review_queue(
        _read_rows(input_path),
        catalog,
        core_concept_ids=args.core_concept_ids,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)
    print(
        json.dumps(
            {
                "output_file": str(output_path),
                "candidate_count": payload["candidate_count"],
                "excluded_count": payload["excluded_count"],
                "coverage_summary": payload["coverage_summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
