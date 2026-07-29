from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.agents.planning_tools import (
    CreateCoursePlanInput,
    PlanningOperation,
    PlanningToolAudit,
    PlanningToolResult,
    UpdateCoursePlanInput,
    build_request_digest,
    build_result_digest,
)
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.planner import CoursePlanner


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
