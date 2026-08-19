"""Prepare human-reviewable evidence decisions without self-publishing evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

ReviewStatus = Literal["review_required", "ready_for_publication", "blocked"]
_REQUIRED_KINDS = ("definition", "code", "exercise")


@dataclass(frozen=True)
class ReviewerDecision:
    evidence_id: str
    approved: bool
    license_confirmed: bool
    reviewer: str
    note: str = ""


@dataclass(frozen=True)
class EvidenceReviewItem:
    evidence_id: str
    content_kind: str | None
    review_status: Literal["review_required", "approved", "rejected"]
    publishable: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceReviewReport:
    status: ReviewStatus
    concept_id: str
    depth: str
    items: tuple[EvidenceReviewItem, ...]
    missing_publishable_kinds: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandidateEvidenceReviewAgent:
    """Evaluate metadata and explicit human decisions for candidate evidence."""

    def review(
        self,
        candidates: tuple[dict[str, Any], ...],
        *,
        concept_id: str,
        depth: str,
        decisions: tuple[ReviewerDecision, ...] = (),
    ) -> EvidenceReviewReport:
        decision_by_id = {decision.evidence_id: decision for decision in decisions}
        if len(decision_by_id) != len(decisions):
            raise ValueError("review decisions have duplicate evidence IDs")

        items = tuple(
            _review_item(candidate, concept_id, depth, decision_by_id.get(_evidence_id(candidate)))
            for candidate in candidates
        )
        publishable_kinds = {
            item.content_kind
            for item in items
            if item.publishable and item.content_kind is not None
        }
        missing = tuple(sorted(set(_REQUIRED_KINDS) - publishable_kinds))
        if missing:
            status: ReviewStatus = "blocked" if decisions else "review_required"
        else:
            status = "ready_for_publication"
        return EvidenceReviewReport(
            status=status,
            concept_id=concept_id,
            depth=depth,
            items=items,
            missing_publishable_kinds=missing,
        )

    def export_template(
        self,
        report: EvidenceReviewReport,
        output_dir: str | Path,
    ) -> tuple[Path, Path]:
        """Export a report and a blank decision template; no evidence is published."""
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        report_path = destination / "06_evidence_review_report.json"
        template_path = destination / "07_reviewer_decision_template.json"
        report_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        template = {
            "instruction": "由具备审核权限的人员逐条填写；资源生成 Agent 不得自行确认。",
            "concept_id": report.concept_id,
            "depth": report.depth,
            "decisions": [
                {
                    "evidence_id": item.evidence_id,
                    "approved": False,
                    "license_confirmed": False,
                    "reviewer": "",
                    "note": "",
                }
                for item in report.items
            ],
        }
        template_path.write_text(
            json.dumps(template, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report_path, template_path

    def build_publication_manifest(
        self,
        report: EvidenceReviewReport,
        candidates: tuple[dict[str, Any], ...],
    ) -> dict[str, object]:
        """Build a manifest only after all required kinds have explicit approval."""
        if report.status != "ready_for_publication":
            raise ValueError("evidence review is not ready for publication")
        candidate_by_id = {_evidence_id(item): item for item in candidates}
        records = []
        for item in report.items:
            if not item.publishable:
                continue
            candidate = candidate_by_id[item.evidence_id]
            records.append(
                {
                    "evidence_id": item.evidence_id,
                    "content_kind": item.content_kind,
                    "review_status": "published",
                    "evidence_status": "published",
                    "license_status": "allowed",
                    "source_title": candidate.get("source_title") or candidate.get("title"),
                    "locator": candidate.get("locator") or candidate.get("heading_path"),
                }
            )
        return {
            "schema_version": "evidence-publication-manifest.v1",
            "concept_id": report.concept_id,
            "depth": report.depth,
            "records": records,
        }

    def export_publication_manifest(
        self,
        manifest: dict[str, object],
        output_dir: str | Path,
    ) -> Path:
        """Export a review-authorized manifest; it does not mutate source evidence."""
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "evidence_publication_manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _review_item(
    candidate: dict[str, Any],
    concept_id: str,
    depth: str,
    decision: ReviewerDecision | None,
) -> EvidenceReviewItem:
    evidence_id = _evidence_id(candidate)
    reasons = _structural_reasons(candidate, concept_id, depth)
    if decision is None:
        reasons.append("等待人工内容审核与许可证确认。")
        return EvidenceReviewItem(
            evidence_id=evidence_id,
            content_kind=_text(candidate.get("content_kind")),
            review_status="review_required",
            publishable=False,
            reasons=tuple(reasons),
        )
    if not decision.reviewer.strip():
        reasons.append("缺少审核人标识。")
    if not decision.approved:
        reasons.append("审核人未批准该证据。")
    license_ok = candidate.get("license_status") == "allowed" or decision.license_confirmed
    if not license_ok:
        reasons.append("许可证未登记为 allowed，且审核人未明确确认。")
    approved = decision.approved and bool(decision.reviewer.strip()) and not reasons
    return EvidenceReviewItem(
        evidence_id=evidence_id,
        content_kind=_text(candidate.get("content_kind")),
        review_status="approved" if approved else "rejected",
        publishable=approved,
        reasons=tuple(reasons),
    )


def _structural_reasons(candidate: dict[str, Any], concept_id: str, depth: str) -> list[str]:
    reasons: list[str] = []
    if _text(candidate.get("concept_id")) != concept_id:
        reasons.append("concept_id 与本次资源目标不一致。")
    if _text(candidate.get("depth")) != depth:
        reasons.append("depth 与本次资源目标不一致。")
    if _text(candidate.get("content_kind")) not in _REQUIRED_KINDS:
        reasons.append("content_kind 不属于 definition、code、exercise。")
    if not (_text(candidate.get("source_id")) or _text(candidate.get("source_title"))):
        reasons.append("缺少来源标识。")
    if not (_text(candidate.get("text")) or _text(candidate.get("excerpt"))):
        reasons.append("缺少可审核文本或摘要。")
    return reasons


def _evidence_id(candidate: dict[str, Any]) -> str:
    for key in ("evidence_id", "chunk_id", "id"):
        value = _text(candidate.get(key))
        if value:
            return value
    return "unidentified_evidence"


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
