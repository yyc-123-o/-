"""Deterministic, no-external-data verification for a persona pipeline snapshot.

This is a distinct, narrower concern from the workplan's planned
``path_accuracy.py`` / ``knowledge_base_coverage.py`` / ``resource_quality.py``
modules: those need external ground truth this project does not have yet
(expert gold labels, real-cohort data). Everything checked here is derivable
from the snapshot itself plus the versioned course catalog -- structural
self-consistency and the invariants the pipeline already claims to hold
(§10 of ``2026-09-02-evaluation-and-validation-workplan.md``), turned into a
pass/fail report with concrete evidence instead of a narrative claim.

Takes an already-parsed snapshot ``Mapping`` (``json.loads(file)`` or
``snapshot.model_dump(mode="python")``), not the strict
``PersonaPipelineSnapshot`` model: a persisted candidate-preview snapshot is
not guaranteed to round-trip through ``model_validate_json`` (see that
model's own docstring), and a verifier that could not check a file it cannot
strictly re-validate would be useless for exactly the runs it most needs to
check.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import RelationKind
from skillforge_kb.planning.ordering import stable_required_concept_ids

from .persona_pipeline import build_persona_snapshot_digest

PERSONA_VERIFICATION_SCHEMA_VERSION = "persona-verification-report.v1"

NodeDict = Mapping[str, object]


class VerificationCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    passed: bool
    message: str = Field(min_length=1)
    sample_size: int | None = Field(default=None, ge=0)
    failures: tuple[str, ...] = ()


class VerificationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["persona-verification-report.v1"] = (
        "persona-verification-report.v1"
    )
    profile_id: str
    path_id: str | None = None
    passed: bool
    checks: tuple[VerificationCheck, ...]
    report_digest: str


def verify_persona_snapshot(
    catalog: OntologyCatalog,
    snapshot: Mapping[str, object],
) -> VerificationReport:
    """Run every check that needs no external ground truth against one
    persona-pipeline snapshot (either mode: one-shot or feedback loop)."""

    checks: list[VerificationCheck] = [_check_no_pipeline_failure(snapshot)]

    full_path = _node_list(snapshot.get("full_path"))
    if snapshot.get("pipeline_failure") is None and full_path:
        checks.append(_check_full_path_matches_catalog(catalog, full_path))
        checks.append(_check_snapshot_digest(snapshot, full_path))
        checks.append(_check_status_partition(snapshot, full_path))
        checks.append(_check_node_depths(snapshot, full_path))
        checks.append(_check_hard_prerequisite_order(catalog, full_path))
        checks.append(_check_resource_mode_matches_gate(full_path))
        checks.append(_check_formal_nodes_have_evidence(full_path))
        checks.append(_check_candidate_nodes_have_audit_report(full_path))
        checks.append(_check_feedback_rounds(snapshot, full_path))

    profile_id = str(snapshot.get("profile_id", ""))
    path_id_raw = snapshot.get("path_id")
    path_id = path_id_raw if isinstance(path_id_raw, str) else None
    passed = all(check.passed for check in checks)
    payload = {
        "profile_id": profile_id,
        "path_id": path_id,
        "checks": [check.model_dump(mode="json") for check in checks],
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return VerificationReport(
        profile_id=profile_id,
        path_id=path_id,
        passed=passed,
        checks=tuple(checks),
        report_digest=f"persona_verification_{digest}",
    )


def _node_list(value: object) -> list[NodeDict]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [cast(NodeDict, item) for item in value if isinstance(item, Mapping)]


def _concept_id(node: NodeDict) -> str:
    return str(node.get("concept_id", ""))


def _check_no_pipeline_failure(snapshot: Mapping[str, object]) -> VerificationCheck:
    failure = snapshot.get("pipeline_failure")
    passed = failure is None
    return VerificationCheck(
        code="no_pipeline_failure",
        passed=passed,
        message=(
            "pipeline_failure is null"
            if passed
            else f"pipeline reported a failure, remaining checks skipped: {failure}"
        ),
    )


def _check_full_path_matches_catalog(
    catalog: OntologyCatalog,
    full_path: list[NodeDict],
) -> VerificationCheck:
    expected = stable_required_concept_ids(catalog)
    actual = [_concept_id(node) for node in full_path]
    if actual == expected:
        return VerificationCheck(
            code="full_path_matches_catalog",
            passed=True,
            message=f"{len(actual)} nodes; concept set and order match the catalog",
            sample_size=len(expected),
        )
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    detail = []
    if missing:
        detail.append(f"missing {len(missing)}")
    if extra:
        detail.append(f"unexpected {len(extra)}")
    if not missing and not extra:
        detail.append("same concept set but different order")
    return VerificationCheck(
        code="full_path_matches_catalog",
        passed=False,
        message="full_path does not match the catalog's required concepts: " + ", ".join(detail),
        sample_size=len(expected),
        failures=tuple(missing + extra),
    )


def _check_snapshot_digest(
    snapshot: Mapping[str, object],
    full_path: list[NodeDict],
) -> VerificationCheck:
    recomputed = build_persona_snapshot_digest(
        str(snapshot.get("profile_id", "")),
        str(snapshot.get("path_id", "")),
        (_concept_id(node) for node in full_path),
        [str(item) for item in _as_sequence(snapshot.get("personalized_path_concept_ids"))],
    )
    stored = snapshot.get("snapshot_digest")
    passed = recomputed == stored
    return VerificationCheck(
        code="snapshot_digest_matches_content",
        passed=passed,
        message=(
            "snapshot_digest matches the recomputed digest"
            if passed
            else f"stored digest {stored!r} does not match recomputed {recomputed!r}"
        ),
    )


def _check_status_partition(
    snapshot: Mapping[str, object],
    full_path: list[NodeDict],
) -> VerificationCheck:
    declared_skipped = {str(item) for item in _as_sequence(snapshot.get("skipped_concept_ids"))}
    declared_personalized = {
        str(item) for item in _as_sequence(snapshot.get("personalized_path_concept_ids"))
    }
    actual_skipped = {_concept_id(node) for node in full_path if node.get("status") == "skipped"}
    actual_personalized = {
        _concept_id(node) for node in full_path if node.get("status") != "skipped"
    }
    failures = sorted(
        (declared_skipped ^ actual_skipped)
        | (declared_personalized ^ actual_personalized)
        | (declared_skipped & declared_personalized)
    )
    passed = not failures
    return VerificationCheck(
        code="status_partition_consistent",
        passed=passed,
        message=(
            "skipped_concept_ids/personalized_path_concept_ids exactly match "
            "each node's status in full_path"
            if passed
            else f"{len(failures)} concept ids disagree with their declared partition"
        ),
        sample_size=len(full_path),
        failures=tuple(failures),
    )


def _check_node_depths(
    snapshot: Mapping[str, object],
    full_path: list[NodeDict],
) -> VerificationCheck:
    node_depths_raw = snapshot.get("node_depths")
    node_depths: Mapping[str, object] = (
        node_depths_raw if isinstance(node_depths_raw, Mapping) else {}
    )
    missing = object()
    failures = [
        _concept_id(node)
        for node in full_path
        if node_depths.get(_concept_id(node), missing) != node.get("delivery_depth")
    ]
    passed = not failures
    return VerificationCheck(
        code="node_depths_consistent",
        passed=passed,
        message=(
            "node_depths matches every node's own delivery_depth"
            if passed
            else f"{len(failures)} of {len(full_path)} nodes disagree with node_depths"
        ),
        sample_size=len(full_path),
        failures=tuple(failures),
    )


def _check_hard_prerequisite_order(
    catalog: OntologyCatalog,
    full_path: list[NodeDict],
) -> VerificationCheck:
    position = {_concept_id(node): index for index, node in enumerate(full_path)}
    hard_pairs = [
        (relation.source, relation.target)
        for relation in catalog.relations(RelationKind.HARD_PREREQUISITE)
        if relation.source in position and relation.target in position
    ]
    violations = sorted(
        f"{source}->{target}"
        for source, target in hard_pairs
        if position[source] >= position[target]
    )
    passed = not violations
    return VerificationCheck(
        code="hard_prerequisite_order",
        passed=passed,
        message=(
            "no hard-prerequisite ordering violations"
            if passed
            else f"{len(violations)} of {len(hard_pairs)} evaluated pairs are out of order"
        ),
        sample_size=len(hard_pairs),
        failures=tuple(violations),
    )


def _check_resource_mode_matches_gate(full_path: list[NodeDict]) -> VerificationCheck:
    failures: list[str] = []
    evaluated = 0
    for node in full_path:
        gate = node.get("generation_gate")
        if not isinstance(gate, Mapping):
            continue
        evaluated += 1
        mode = node.get("resource_mode")
        blocking = {str(item) for item in _as_sequence(gate.get("blocking_codes"))}
        ok: bool
        if mode == "formal":
            ok = gate.get("allowed") is True
        elif mode == "candidate_draft":
            ok = blocking == {"blocked_missing_published_evidence"}
        elif mode == "blocked_hard_prerequisite":
            ok = "blocked_hard_prerequisite" in blocking
        elif mode == "not_attempted":
            ok = bool(node.get("retrieval_error")) or bool(node.get("resource_error"))
        else:
            ok = False
        if not ok:
            failures.append(_concept_id(node))
    passed = not failures
    return VerificationCheck(
        code="resource_mode_matches_generation_gate",
        passed=passed,
        message=(
            "resource_mode is consistent with generation_gate for every processed node"
            if passed
            else f"{len(failures)} of {evaluated} processed nodes disagree"
        ),
        sample_size=evaluated,
        failures=tuple(failures),
    )


def _check_formal_nodes_have_evidence(full_path: list[NodeDict]) -> VerificationCheck:
    formal_nodes = [node for node in full_path if node.get("resource_mode") == "formal"]
    failures = []
    for node in formal_nodes:
        summary = node.get("evidence_summary")
        count = summary.get("formal_evidence_count") if isinstance(summary, Mapping) else None
        if not isinstance(count, int) or count <= 0:
            failures.append(_concept_id(node))
    passed = not failures
    return VerificationCheck(
        code="formal_nodes_have_published_evidence",
        passed=passed,
        message=(
            "every formal-mode node has formal_evidence_count > 0"
            if passed
            else f"{len(failures)} of {len(formal_nodes)} formal nodes have no counted evidence"
        ),
        sample_size=len(formal_nodes),
        failures=tuple(failures),
    )


def _check_candidate_nodes_have_audit_report(full_path: list[NodeDict]) -> VerificationCheck:
    candidate_nodes = [
        node for node in full_path if node.get("resource_mode") == "candidate_draft"
    ]
    failures = []
    for node in candidate_nodes:
        resource_result = node.get("resource_result")
        preview_package = (
            resource_result.get("preview_package")
            if isinstance(resource_result, Mapping)
            else None
        )
        audit_report = (
            preview_package.get("audit_report") if isinstance(preview_package, Mapping) else None
        )
        if audit_report is None:
            failures.append(_concept_id(node))
    passed = not failures
    return VerificationCheck(
        code="candidate_drafts_have_audit_report",
        passed=passed,
        message=(
            "every candidate_draft resource carries a ResourceAuditor audit_report"
            if passed
            else f"{len(failures)} of {len(candidate_nodes)} candidate drafts have no audit_report"
        ),
        sample_size=len(candidate_nodes),
        failures=tuple(failures),
    )


def _check_feedback_rounds(
    snapshot: Mapping[str, object],
    full_path: list[NodeDict],
) -> VerificationCheck:
    rounds = [
        item for item in _as_sequence(snapshot.get("feedback_rounds")) if isinstance(item, Mapping)
    ]
    if not rounds:
        return VerificationCheck(
            code="feedback_rounds_consistent",
            passed=True,
            message="no feedback rounds to check (one-shot snapshot)",
            sample_size=0,
        )
    round_concept_ids = [str(item.get("concept_id", "")) for item in rounds]
    duplicates = sorted({c for c in round_concept_ids if round_concept_ids.count(c) > 1})
    nodes_by_id = {_concept_id(node): node for node in full_path}
    not_completed = [
        concept_id
        for concept_id in round_concept_ids
        if nodes_by_id.get(concept_id, {}).get("status") != "completed"
    ]
    failures = tuple(sorted({*duplicates, *not_completed}))
    passed = not failures
    return VerificationCheck(
        code="feedback_rounds_consistent",
        passed=passed,
        message=(
            "every round's concept is unique and ended up completed in full_path"
            if passed
            else f"{len(failures)} of {len(rounds)} rounds are duplicated or never completed"
        ),
        sample_size=len(rounds),
        failures=failures,
    )


def _as_sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return ()
