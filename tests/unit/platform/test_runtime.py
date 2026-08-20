from pathlib import Path

import pytest

from skillforge_kb.platform.models import PlatformRunRequest
from skillforge_kb.platform.runtime import (
    DefaultPlatformPaths,
    build_default_platform_service,
    validate_default_platform_paths,
)


def test_default_paths_are_resolved_from_project_root(tmp_path: Path) -> None:
    paths = DefaultPlatformPaths.from_project_root(tmp_path)

    assert paths.course_file == tmp_path / "resources" / "ontology" / "ai_course_v1.yaml"
    assert paths.evidence_file == (
        tmp_path / "resources" / "evidence" / "evidence_manifest_v1.yaml"
    )
    assert paths.knowledge_file == tmp_path / "data" / "index_chunks.jsonl"
    assert paths.candidate_knowledge_file == (
        tmp_path / "resources" / "knowledge" / "cnn_convolution_candidates.jsonl"
    )


def test_runtime_builds_without_network_or_services(profile) -> None:
    root = Path(__file__).parents[3]
    service = build_default_platform_service(root)
    request = PlatformRunRequest(profile=profile, idempotency_key="runtime-build")

    assert service.peek(request) is None


def test_runtime_reports_first_missing_required_file(tmp_path: Path) -> None:
    paths = DefaultPlatformPaths.from_project_root(tmp_path)

    with pytest.raises(ValueError, match="ai_course_v1.yaml"):
        validate_default_platform_paths(paths)
