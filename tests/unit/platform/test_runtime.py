from pathlib import Path

import pytest

from skillforge_kb.agents.planning_agent_models import PlanningAgentEvent, PlanningEventKind
from skillforge_kb.platform.models import PlatformRunRequest, build_run_id
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
    assert not hasattr(paths, "candidate_knowledge_file")


def test_runtime_builds_without_network_or_services(profile) -> None:
    root = Path(__file__).parents[3]
    service = build_default_platform_service(root)
    request = PlatformRunRequest(profile=profile, idempotency_key="runtime-build-test")

    assert service.peek(request) is None


def test_runtime_uses_a_reopenable_sqlite_state_store(profile, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SKILLFORGE_PLATFORM_STATE_DB", str(tmp_path / "platform.sqlite3"))
    root = Path(__file__).parents[3]
    first = build_default_platform_service(root)
    try:
        request = PlatformRunRequest(profile=profile, idempotency_key="runtime-persisted")
        assert first.peek(request) is None
        first._repository.reserve(request)
    finally:
        first.close()

    second = build_default_platform_service(root)
    try:
        assert second.peek(request) is None
        assert second._repository.get_request(build_run_id(request)) == request
    finally:
        second.close()


def test_runtime_persists_planning_checkpoint_across_service_restarts(
    profile,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SKILLFORGE_PLATFORM_STATE_DB", str(tmp_path / "platform.sqlite3"))
    root = Path(__file__).parents[3]
    thread_id = "runtime-restart-thread"
    event = PlanningAgentEvent(
        event_id="event_" + "a" * 64,
        kind=PlanningEventKind.INITIALIZE,
        profile=profile,
    )

    first = build_default_platform_service(root)
    initial = first._dependencies.planning_agent.invoke(event, thread_id)
    assert initial.path is not None
    first.close()

    second = build_default_platform_service(root)
    restored = second._dependencies.planning_agent.get_state(thread_id)
    second.close()

    assert restored is not None
    assert restored.path == initial.path


def test_runtime_reports_first_missing_required_file(tmp_path: Path) -> None:
    paths = DefaultPlatformPaths.from_project_root(tmp_path)

    with pytest.raises(ValueError, match="ai_course_v1.yaml"):
        validate_default_platform_paths(paths)
