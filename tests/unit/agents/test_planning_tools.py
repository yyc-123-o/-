from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.agents.planning_tools import (
    CreateCoursePlanInput,
    PlanningFailureCode,
    PlanningNodeStatus,
    PlanningOperation,
    PlanningToolAudit,
    PlanningToolResult,
    UpdateCoursePlanInput,
    build_create_course_plan_node,
    build_request_digest,
    build_result_digest,
    build_update_course_plan_node,
    create_course_plan_tool,
    update_course_plan_tool,
)
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.planning.updater import DepthUpdater


@pytest.fixture
def profile(catalog) -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-agent-adapter",
        learner_ref="a" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


def test_request_contracts_reject_duplicate_completed_ids(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)

    with pytest.raises(ValidationError, match="completed concept IDs must be unique"):
        CreateCoursePlanInput(
            profile=profile,
            completed_concept_ids=("math.linear-algebra.scalar",) * 2,
        )
    with pytest.raises(ValidationError, match="completed concept IDs must be unique"):
        UpdateCoursePlanInput(
            existing=existing,
            profile=profile,
            completed_concept_ids=("math.linear-algebra.scalar",) * 2,
        )


def test_update_request_requires_a_completed_concept(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)

    with pytest.raises(ValidationError):
        UpdateCoursePlanInput(
            existing=existing,
            profile=profile,
            completed_concept_ids=(),
        )


def test_request_digest_treats_completed_ids_as_an_unordered_set(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)
    policy_digest = existing.policy_digest
    first = CreateCoursePlanInput(
        profile=profile,
        completed_concept_ids=(
            "math.linear-algebra.vector",
            "math.linear-algebra.scalar",
        ),
    )
    second = CreateCoursePlanInput(
        profile=profile,
        completed_concept_ids=tuple(reversed(first.completed_concept_ids)),
    )

    assert build_request_digest(PlanningOperation.CREATE, first, policy_digest) == (
        build_request_digest(PlanningOperation.CREATE, second, policy_digest)
    )


def test_result_digest_rejects_path_mutation(catalog, profile) -> None:
    path = CoursePlanner(catalog).plan(profile)
    request = CreateCoursePlanInput(profile=profile)
    request_digest = build_request_digest(
        PlanningOperation.CREATE,
        request,
        path.policy_digest,
    )
    result_digest = build_result_digest(
        PlanningOperation.CREATE,
        request_digest,
        path,
    )
    result = PlanningToolResult(
        path=path,
        audit=PlanningToolAudit(
            operation=PlanningOperation.CREATE,
            request_digest=request_digest,
            result_digest=result_digest,
            path_id=path.path_id,
            profile_id=path.profile_id,
            graph_version=path.graph_version,
            policy_digest=path.policy_digest,
        ),
    )
    changed = result.path.model_copy(
        update={"generated_at": datetime(2026, 7, 30, tzinfo=UTC)}
    )
    invalid = result.model_copy(update={"path": changed})

    with pytest.raises(ValidationError, match="result digest"):
        PlanningToolResult.model_validate(invalid.model_dump())


def test_result_rejects_inconsistent_audit_identity(catalog, profile) -> None:
    path = CoursePlanner(catalog).plan(profile)
    request = CreateCoursePlanInput(profile=profile)
    request_digest = build_request_digest(
        PlanningOperation.CREATE,
        request,
        path.policy_digest,
    )
    result_digest = build_result_digest(
        PlanningOperation.CREATE,
        request_digest,
        path,
    )
    invalid_audit = PlanningToolAudit(
        operation=PlanningOperation.CREATE,
        request_digest=request_digest,
        result_digest=result_digest,
        path_id="path_" + "0" * 64,
        profile_id=path.profile_id,
        graph_version=path.graph_version,
        policy_digest=path.policy_digest,
    )

    with pytest.raises(ValidationError, match="audit path ID"):
        PlanningToolResult(path=path, audit=invalid_audit)


def test_create_tool_matches_planner_and_is_idempotent(catalog, profile) -> None:
    tool = create_course_plan_tool(catalog)
    payload = {"profile": profile.model_dump(mode="json")}

    first = PlanningToolResult.model_validate(tool.invoke(payload))
    second = PlanningToolResult.model_validate(tool.invoke(payload))

    assert tool.name == "create_course_plan"
    assert "deterministic" in tool.description.lower()
    assert tool.args_schema is CreateCoursePlanInput
    assert first == second
    assert first.path == CoursePlanner(catalog).plan(profile)
    assert first.audit.path_id == first.path.path_id


def test_create_tool_digest_ignores_completed_id_order(catalog, profile) -> None:
    tool = create_course_plan_tool(catalog)
    completed_ids = [
        "math.linear-algebra.scalar",
        "math.linear-algebra.vector",
    ]
    payload = {
        "profile": profile.model_dump(mode="json"),
        "completed_concept_ids": completed_ids,
    }
    reversed_payload = {
        **payload,
        "completed_concept_ids": list(reversed(completed_ids)),
    }

    first = PlanningToolResult.model_validate(tool.invoke(payload))
    second = PlanningToolResult.model_validate(tool.invoke(reversed_payload))

    assert first.audit.request_digest == second.audit.request_digest
    assert first == second


def test_update_tool_matches_updater_and_preserves_path_identity(
    catalog,
    profile,
) -> None:
    existing = CoursePlanner(catalog).plan(profile)
    completed = existing.nodes[0].concept_id
    tool = update_course_plan_tool(catalog)
    payload = {
        "existing": existing.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "completed_concept_ids": [completed],
    }

    result = PlanningToolResult.model_validate(tool.invoke(payload))
    expected = DepthUpdater(catalog).update(existing, profile, {completed})

    assert tool.name == "update_course_plan"
    assert tool.args_schema is UpdateCoursePlanInput
    assert result.path == expected
    assert result.path.path_id == existing.path_id
    assert [node.concept_id for node in result.path.nodes] == [
        node.concept_id for node in existing.nodes
    ]


def test_tool_rejects_unknown_completed_concept(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)

    with pytest.raises(ValueError, match="completed concept"):
        update_course_plan_tool(catalog).invoke(
            {
                "existing": existing.model_dump(mode="json"),
                "profile": profile.model_dump(mode="json"),
                "completed_concept_ids": ["unknown.concept"],
            }
        )


def test_create_node_returns_planned_state(catalog, profile) -> None:
    update = build_create_course_plan_node(catalog)({"profile": profile})

    assert update["planning_status"] is PlanningNodeStatus.PLANNED
    assert update["path"].profile_id == profile.profile_id
    assert update["planning_audit"] is not None
    assert update["planning_audit"].path_id == update["path"].path_id
    assert update["planning_failure"] is None


def test_create_node_returns_invalid_state_for_missing_profile(catalog) -> None:
    update = build_create_course_plan_node(catalog)({})

    assert update["planning_status"] is PlanningNodeStatus.FAILED
    assert update["planning_audit"] is None
    assert update["planning_failure"] is not None
    assert update["planning_failure"].code is PlanningFailureCode.INVALID_STATE
    assert "profile" in update["planning_failure"].message
    assert "path" not in update


def test_create_node_returns_planning_error_for_graph_mismatch(
    catalog,
    profile,
) -> None:
    invalid_profile = profile.model_copy(update={"graph_version": "ai-course-v2"})

    update = build_create_course_plan_node(catalog)({"profile": invalid_profile})

    assert update["planning_status"] is PlanningNodeStatus.FAILED
    assert update["planning_failure"] is not None
    assert update["planning_failure"].code is PlanningFailureCode.PLANNING_ERROR
    assert "graph version" in update["planning_failure"].message


def test_update_node_returns_updated_state_and_preserves_identity(
    catalog,
    profile,
) -> None:
    existing = CoursePlanner(catalog).plan(profile)
    completed = existing.nodes[0].concept_id

    update = build_update_course_plan_node(catalog)(
        {
            "profile": profile,
            "path": existing,
            "completed_concept_ids": (completed,),
        }
    )

    assert update["planning_status"] is PlanningNodeStatus.UPDATED
    assert update["path"].path_id == existing.path_id
    assert update["planning_audit"] is not None
    assert update["planning_failure"] is None


def test_update_node_failure_does_not_replace_existing_path(catalog, profile) -> None:
    existing = CoursePlanner(catalog).plan(profile)

    update = build_update_course_plan_node(catalog)(
        {
            "profile": profile,
            "path": existing,
            "completed_concept_ids": ("unknown.concept",),
        }
    )

    assert update["planning_status"] is PlanningNodeStatus.FAILED
    assert update["planning_audit"] is None
    assert update["planning_failure"] is not None
    assert update["planning_failure"].code is PlanningFailureCode.PLANNING_ERROR
    assert "path" not in update


def test_planning_adapter_is_available_from_agents_public_api() -> None:
    from skillforge_kb import agents

    assert agents.CreateCoursePlanInput is CreateCoursePlanInput
    assert agents.PlanningToolResult is PlanningToolResult
    assert agents.create_course_plan_tool is create_course_plan_tool
    assert agents.update_course_plan_tool is update_course_plan_tool
    assert agents.build_create_course_plan_node is build_create_course_plan_node
    assert agents.build_update_course_plan_node is build_update_course_plan_node
