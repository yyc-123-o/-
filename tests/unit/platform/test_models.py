import pytest
from pydantic import ValidationError

from skillforge_kb.platform.models import (
    AssessmentModel,
    ExecutionMode,
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    build_request_digest,
    build_run_id,
)


def test_assessment_model_defaults_to_rule(profile) -> None:
    request = PlatformRunRequest(profile=profile, idempotency_key="model-default")

    assert request.assessment_model is AssessmentModel.RULE


def test_bkt_model_changes_request_digest_but_not_run_id(profile) -> None:
    rule = PlatformRunRequest(profile=profile, idempotency_key="model-digest")
    bkt = rule.model_copy(update={"assessment_model": AssessmentModel.BKT})

    assert build_request_digest(rule) != build_request_digest(bkt)
    assert build_run_id(rule) == build_run_id(bkt)


def test_invalid_assessment_model_is_rejected(profile) -> None:
    with pytest.raises(ValidationError):
        PlatformRunRequest(
            profile=profile,
            idempotency_key="model-invalid",
            assessment_model="unsupported",
        )


def test_request_builds_stable_digest_and_run_id(profile) -> None:
    request = PlatformRunRequest(
        profile=profile,
        idempotency_key="demo-run-1",
        execution_mode=ExecutionMode.STRICT,
        top_k=5,
    )

    assert build_run_id(request) == build_run_id(request.model_copy())
    assert build_run_id(request).startswith("run_")
    assert build_request_digest(request).startswith("request_")


def test_target_concept_changes_request_digest(profile) -> None:
    base = PlatformRunRequest(profile=profile, idempotency_key="target-digest")
    targeted = base.model_copy(update={"target_concept_id": "dl.cnn.convolution"})

    assert build_request_digest(base) != build_request_digest(targeted)


def test_completed_result_requires_resources(profile) -> None:
    request = PlatformRunRequest(profile=profile, idempotency_key="complete-run")
    with pytest.raises(ValueError, match="completed run requires resources"):
        PlatformRunResult(
            run_id=build_run_id(request),
            request_digest=build_request_digest(request),
            profile_id=profile.profile_id,
            status=PlatformRunStatus.COMPLETED,
        )


def test_blocked_result_requires_evidence_gap(profile) -> None:
    request = PlatformRunRequest(profile=profile, idempotency_key="blocked-run")
    with pytest.raises(ValueError, match="blocked run requires an evidence gap"):
        PlatformRunResult(
            run_id=build_run_id(request),
            request_digest=build_request_digest(request),
            profile_id=profile.profile_id,
            status=PlatformRunStatus.BLOCKED,
        )
