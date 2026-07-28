import json
from pathlib import Path

from skillforge_kb.fusion.jsonl import iter_jsonl

from .catalog import OntologyCatalog
from .models import CoverageReport


def analyze_candidate_coverage(catalog: OntologyCatalog, jsonl_path: Path) -> CoverageReport:
    known_ids = {concept.id for concept in catalog.concepts()}
    counts = {concept_id: 0 for concept_id in sorted(known_ids)}
    unknown_ids: set[str] = set()
    invalid_lines: list[int] = []

    for record in iter_jsonl(jsonl_path):
        if record.value is None:
            invalid_lines.append(record.line_number)
            continue
        raw_ids = record.value.get("concept_ids", [])
        if not isinstance(raw_ids, list):
            continue
        for raw_id in raw_ids:
            if not isinstance(raw_id, str):
                continue
            if raw_id in known_ids:
                counts[raw_id] += 1
            else:
                unknown_ids.add(raw_id)

    return CoverageReport(
        graph_version=catalog.course_document.version,
        candidate_counts=counts,
        coverage_gap_ids=[concept_id for concept_id, count in counts.items() if count == 0],
        unknown_concept_ids=sorted(unknown_ids),
        invalid_json_lines=invalid_lines,
        published_concept_ids=(),
    )


def write_coverage_report(report: CoverageReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    serialized = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    temporary_path.write_text(serialized + "\n", encoding="utf-8")
    temporary_path.replace(output_path)
