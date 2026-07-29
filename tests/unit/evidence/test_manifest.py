from pathlib import Path

import yaml

from skillforge_kb.domain.enums import ContentKind, Language
from skillforge_kb.evidence.manifest import EvidenceIndex, load_evidence_index
from skillforge_kb.ontology.models import DepthLevel


def _write_manifest(path: Path) -> None:
    raw = {
        "version": "evidence-manifest-v1",
        "graph_version": "ai-course-v1",
        "records": [
            {
                "evidence_id": "evidence_" + "b" * 64,
                "graph_version": "ai-course-v1",
                "source_id": "source-2",
                "chunk_id": "chunk-2",
                "concept_id": "math.linear-algebra.scalar",
                "depth": "intro",
                "source_url": "https://example.edu/source-2",
                "locator": "section 2",
                "normalized_hash": "c" * 64,
                "language": "en",
                "content_kind": "definition",
                "difficulty": 1,
                "license_status": "allowed",
                "review_status": "published",
                "reviewed_by": "reviewer-1",
                "reviewed_at": "2026-07-29T00:00:00Z",
            },
            {
                "evidence_id": "evidence_" + "a" * 64,
                "graph_version": "ai-course-v1",
                "source_id": "source-1",
                "chunk_id": "chunk-1",
                "concept_id": "math.linear-algebra.scalar",
                "depth": "intro",
                "source_url": "https://example.edu/source-1",
                "locator": "section 1",
                "normalized_hash": "d" * 64,
                "language": "en",
                "content_kind": "definition",
                "difficulty": 1,
                "license_status": "pending",
                "review_status": "candidate",
            },
        ],
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def test_index_returns_only_published_evidence_in_stable_order(tmp_path, catalog) -> None:
    path = tmp_path / "evidence.yaml"
    _write_manifest(path)
    index = load_evidence_index(catalog, path)

    rows = index.query(
        "math.linear-algebra.scalar",
        DepthLevel.INTRO,
        Language.EN,
        ContentKind.DEFINITION,
    )

    assert [row.source_id for row in rows] == ["source-2"]


def test_empty_manifest_is_a_valid_coverage_gap(catalog) -> None:
    index = EvidenceIndex(
        version="evidence-manifest-v1",
        graph_version=catalog.course_document.version,
        records=(),
    )

    assert index.query("math.linear-algebra.scalar", DepthLevel.INTRO) == ()
