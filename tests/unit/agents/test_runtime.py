import json
from pathlib import Path

import pytest

from skillforge_kb.agents.planning_agent_models import PlanningAgentStatus
from skillforge_kb.agents.runtime import (
    StandaloneAgentPaths,
    load_planning_event,
    run_standalone_event,
)


def test_runtime_loads_default_assets_and_runs_initialize() -> None:
    paths = StandaloneAgentPaths.from_project_root(Path.cwd())
    event = load_planning_event(Path("examples/agents/initialize_event.json"))

    result = run_standalone_event(paths, event, "runtime-test")

    assert result.status is PlanningAgentStatus.READY
    assert result.path is not None
    assert result.current_node is not None
    assert result.knowledge_context is not None


def test_loader_rejects_noncanonical_profile(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"profile_meta": {"profile_id": "legacy"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid planning event"):
        load_planning_event(path)
