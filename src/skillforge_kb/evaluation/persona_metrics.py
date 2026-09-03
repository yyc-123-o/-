"""The three competition hard metrics, measured from persona-pipeline snapshots.

XH-202630's evaluation criteria name three numeric thresholds that must be
measured, not argued for: hallucination rate < 5%, learner-resource
difficulty adaptation accuracy >= 85%, core-concept coverage >= 90%. This
module computes all three from snapshots :mod:`persona_pipeline` already
produces -- it introduces no new generation or audit logic, only aggregation
and reporting.

Precision differs by metric, and each report says so explicitly rather than
presenting three equally-authoritative numbers:

- ``coverage``: exact, but only when measured against a *natural-completion*
  :func:`~.persona_pipeline.run_persona_feedback_loop` snapshot (no
  ``max_rounds`` cap), not a one-shot :func:`~.persona_pipeline.run_persona_pipeline`
  snapshot. A one-shot snapshot only "unlocks" nodes whose hard prerequisites
  the learner's *current* diagnosed profile already satisfies -- it drastically
  understates coverage for everything the learner has not reached yet (measured
  7-22% on a one-shot run versus ~98.5% on the same profile run to natural
  completion). Whether a resource was produced at all does not depend on
  generation quality, so no real LLM call is required either way.
- ``adaptation``: a **named proxy**, not an expert-graded accuracy. There is
  no expert-labelled ground truth for "this resource's difficulty correctly
  matches this learner" in this project yet (the workplan says so too), so
  this checks a concrete, honestly-described stand-in instead: does the
  delivered student quiz's modal (most common) difficulty level match the
  depth planning decided for that node (`intro` -> 1, `intermediate` -> 2,
  `advanced` -> 3)? Computed from the same natural-completion snapshot as
  coverage.
- ``hallucination``: exact, but over a **disclosed sample**, not the whole
  course. Meaningful only for genuinely LLM-generated content -- a
  deterministic fallback draft trivially "supports" itself and would report
  a false near-zero rate -- so this only counts nodes whose
  ``trace.model_name`` is not ``FakeLLMAdapter``'s fixed
  ``"fake-resource-writer"`` sentinel, typically supplied by running
  :func:`~.persona_pipeline.run_persona_feedback_loop` with ``max_rounds``
  set to a small number against a configured real adapter. ``sampled_node_count``
  is always reported alongside the rate.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

PERSONA_HARD_METRICS_SCHEMA_VERSION = "persona-hard-metrics-report.v1"

_FALLBACK_MODEL_NAME = "fake-resource-writer"

_EXPECTED_MODAL_DIFFICULTY: Mapping[str, int] = {
    "intro": 1,
    "intermediate": 2,
    "advanced": 3,
}

NodeDict = Mapping[str, object]


class CoverageStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempted_nodes: int = Field(ge=0)
    covered_nodes: int = Field(ge=0)
    coverage_rate: float = Field(ge=0, le=1)


class AdaptationStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checked_nodes: int = Field(ge=0)
    matched_nodes: int = Field(ge=0)
    adaptation_accuracy: float = Field(ge=0, le=1)


class ClaimStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_claims: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    hallucination_rate: float = Field(ge=0, le=1)
    sampled_node_count: int = Field(ge=0)


class PersonaHardMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    persona_label: str = Field(min_length=1)
    profile_id: str
    coverage: CoverageStats
    adaptation: AdaptationStats
    hallucination: ClaimStats | None = None


class HardMetricsReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["persona-hard-metrics-report.v1"] = (
        "persona-hard-metrics-report.v1"
    )
    personas: tuple[PersonaHardMetrics, ...]
    aggregate_coverage: CoverageStats
    aggregate_adaptation: AdaptationStats
    aggregate_hallucination: ClaimStats
    thresholds_met: dict[str, bool]
    report_digest: str


def _node_list(value: object) -> list[NodeDict]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [cast(NodeDict, item) for item in value if isinstance(item, Mapping)]


def _preview_package(node: NodeDict) -> Mapping[str, object] | None:
    resource_result = node.get("resource_result")
    if not isinstance(resource_result, Mapping):
        return None
    preview = resource_result.get("preview_package")
    return preview if isinstance(preview, Mapping) else None


def _coverage_stats(full_path: Sequence[NodeDict]) -> CoverageStats:
    attempted = [node for node in full_path if node.get("status") != "skipped"]
    covered = [
        node for node in attempted if node.get("resource_mode") in {"formal", "candidate_draft"}
    ]
    rate = len(covered) / len(attempted) if attempted else 0.0
    return CoverageStats(
        attempted_nodes=len(attempted), covered_nodes=len(covered), coverage_rate=rate
    )


def _adaptation_stats(full_path: Sequence[NodeDict]) -> AdaptationStats:
    """Only ``candidate_draft`` nodes carry a draft in this repo today (no
    published evidence means ``formal`` mode never triggers) -- see the
    module docstring. A node without a readable draft/depth is skipped, not
    counted as a mismatch."""

    checked = 0
    matched = 0
    for node in full_path:
        depth = node.get("delivery_depth")
        expected = _EXPECTED_MODAL_DIFFICULTY.get(str(depth)) if depth is not None else None
        if expected is None:
            continue
        preview = _preview_package(node)
        if preview is None:
            continue
        draft = preview.get("draft")
        if not isinstance(draft, Mapping):
            continue
        quiz = draft.get("student_quiz")
        if not isinstance(quiz, Mapping):
            continue
        items = quiz.get("items")
        if not isinstance(items, Sequence) or isinstance(items, str | bytes):
            continue
        difficulties = [
            item.get("difficulty")
            for item in items
            if isinstance(item, Mapping) and isinstance(item.get("difficulty"), int)
        ]
        if not difficulties:
            continue
        checked += 1
        modal_difficulty = Counter(difficulties).most_common(1)[0][0]
        if modal_difficulty == expected:
            matched += 1
    rate = matched / checked if checked else 0.0
    return AdaptationStats(checked_nodes=checked, matched_nodes=matched, adaptation_accuracy=rate)


def _claim_stats(full_path: Sequence[NodeDict]) -> ClaimStats:
    """Only counts nodes a real (non-fallback) adapter generated -- see the
    module docstring for why a fallback-generated node would understate the
    rate."""

    total = 0
    unsupported = 0
    sampled_nodes = 0
    for node in full_path:
        preview = _preview_package(node)
        if preview is None:
            continue
        trace = preview.get("trace")
        model_name = trace.get("model_name") if isinstance(trace, Mapping) else None
        if model_name is None or model_name == _FALLBACK_MODEL_NAME:
            continue
        audit_report = preview.get("audit_report")
        if not isinstance(audit_report, Mapping):
            continue
        ledger = audit_report.get("claim_evidence_ledger")
        if not isinstance(ledger, Sequence) or isinstance(ledger, str | bytes):
            continue
        node_claims = [item for item in ledger if isinstance(item, Mapping)]
        if not node_claims:
            continue
        sampled_nodes += 1
        total += len(node_claims)
        unsupported += sum(1 for item in node_claims if item.get("support") == "unsupported")
    rate = unsupported / total if total else 0.0
    return ClaimStats(
        total_claims=total,
        unsupported_claims=unsupported,
        hallucination_rate=rate,
        sampled_node_count=sampled_nodes,
    )


def compute_persona_hard_metrics(
    label: str,
    coverage_snapshot: Mapping[str, object],
    hallucination_snapshot: Mapping[str, object] | None,
) -> PersonaHardMetrics:
    """``coverage_snapshot`` should come from a ``run_persona_feedback_loop``
    run with no ``max_rounds`` cap (natural completion) -- NOT a one-shot
    ``run_persona_pipeline`` run, which only unlocks nodes whose prerequisites
    the learner's current profile already satisfies and severely understates
    coverage (see the module docstring). ``hallucination_snapshot``, if given,
    should come from a ``run_persona_feedback_loop`` run against a configured
    real adapter -- typically with a small ``max_rounds`` -- and is optional
    because hallucination measurement needs a real model call while coverage
    and adaptation do not."""

    coverage_path = _node_list(coverage_snapshot.get("full_path"))
    hallucination = (
        _claim_stats(_node_list(hallucination_snapshot.get("full_path")))
        if hallucination_snapshot is not None
        else None
    )
    return PersonaHardMetrics(
        persona_label=label,
        profile_id=str(coverage_snapshot.get("profile_id", "")),
        coverage=_coverage_stats(coverage_path),
        adaptation=_adaptation_stats(coverage_path),
        hallucination=hallucination,
    )


def aggregate_hard_metrics(personas: Sequence[PersonaHardMetrics]) -> HardMetricsReport:
    attempted = sum(p.coverage.attempted_nodes for p in personas)
    covered = sum(p.coverage.covered_nodes for p in personas)
    checked = sum(p.adaptation.checked_nodes for p in personas)
    matched = sum(p.adaptation.matched_nodes for p in personas)
    hallucinations = [p.hallucination for p in personas if p.hallucination is not None]
    total_claims = sum(h.total_claims for h in hallucinations)
    unsupported_claims = sum(h.unsupported_claims for h in hallucinations)
    sampled_nodes = sum(h.sampled_node_count for h in hallucinations)

    aggregate_coverage = CoverageStats(
        attempted_nodes=attempted,
        covered_nodes=covered,
        coverage_rate=covered / attempted if attempted else 0.0,
    )
    aggregate_adaptation = AdaptationStats(
        checked_nodes=checked,
        matched_nodes=matched,
        adaptation_accuracy=matched / checked if checked else 0.0,
    )
    aggregate_hallucination = ClaimStats(
        total_claims=total_claims,
        unsupported_claims=unsupported_claims,
        hallucination_rate=unsupported_claims / total_claims if total_claims else 0.0,
        sampled_node_count=sampled_nodes,
    )
    thresholds_met = {
        "hallucination_rate_below_5pct": aggregate_hallucination.hallucination_rate < 0.05,
        "adaptation_accuracy_at_least_85pct": aggregate_adaptation.adaptation_accuracy >= 0.85,
        "coverage_rate_at_least_90pct": aggregate_coverage.coverage_rate >= 0.90,
    }
    payload = {
        "personas": [p.model_dump(mode="json") for p in personas],
        "aggregate_coverage": aggregate_coverage.model_dump(mode="json"),
        "aggregate_adaptation": aggregate_adaptation.model_dump(mode="json"),
        "aggregate_hallucination": aggregate_hallucination.model_dump(mode="json"),
        "thresholds_met": thresholds_met,
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return HardMetricsReport(
        personas=tuple(personas),
        aggregate_coverage=aggregate_coverage,
        aggregate_adaptation=aggregate_adaptation,
        aggregate_hallucination=aggregate_hallucination,
        thresholds_met=thresholds_met,
        report_digest=f"persona_hard_metrics_{digest}",
    )
