from pathlib import Path

from skillforge_kb.agents.planning_agent_models import PlanningAgentStatus
from skillforge_kb.agents.runtime import (
    StandaloneAgentPaths,
    load_planning_event,
    run_standalone_event,
)
from skillforge_kb.retrieval.models import KnowledgeRetrievalStatus


def test_math_node_does_not_return_unrelated_project_context() -> None:
    paths = StandaloneAgentPaths.from_project_root(Path.cwd())
    event = load_planning_event(Path("examples/agents/initialize_event.json"))

    result = run_standalone_event(paths, event, "precision-demo")

    assert result.status is PlanningAgentStatus.READY
    assert result.current_node is not None
    assert result.current_node.concept_id == "math.linear-algebra.scalar"
    assert result.knowledge_context is not None
    assert result.knowledge_context.status is KnowledgeRetrievalStatus.NO_RESULTS
    assert result.knowledge_context.hits == ()
