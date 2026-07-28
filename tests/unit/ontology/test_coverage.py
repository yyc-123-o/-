import json

from skillforge_kb.ontology.coverage import analyze_candidate_coverage, write_coverage_report


def test_coverage_counts_known_candidates_without_publishing(tmp_path, catalog) -> None:
    path = tmp_path / "candidate.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"concept_ids": ["ml.optimization.gradient-descent"]}),
                json.dumps({"concept_ids": ["unknown.concept"]}),
                "{not-json}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = analyze_candidate_coverage(catalog, path)

    assert report.candidate_counts["ml.optimization.gradient-descent"] == 1
    assert report.unknown_concept_ids == ["unknown.concept"]
    assert report.invalid_json_lines == [3]
    assert report.published_concept_ids == ()

    output = tmp_path / "coverage.json"
    write_coverage_report(report, output)
    assert json.loads(output.read_text(encoding="utf-8"))["published_concept_ids"] == []
