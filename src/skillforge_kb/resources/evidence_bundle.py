import json
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.domain.enums import LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import EvidenceRecord, EvidenceReviewStatus
from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel

from .models import ResourceBrief


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_id: str = Field(pattern=r"^bundle_[0-9a-f]{64}$")
    brief_id: str = Field(pattern=r"^brief_[0-9a-f]{64}$")
    graph_version: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    records: tuple[EvidenceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_records(self) -> "EvidenceBundle":
        evidence_ids = [record.evidence_id for record in self.records]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence bundle IDs must be unique")
        for record in self.records:
            if record.graph_version != self.graph_version:
                raise ValueError("evidence bundle graph version mismatch")
            if record.concept_id != self.concept_id or record.depth is not self.depth:
                raise ValueError("evidence bundle scope mismatch")
            if record.review_status is not EvidenceReviewStatus.PUBLISHED:
                raise ValueError("evidence bundle requires published evidence")
            if record.license_status is not LicenseStatus.ALLOWED:
                raise ValueError("evidence bundle requires allowed evidence")
        return self


def build_evidence_bundle(
    brief: ResourceBrief,
    index: EvidenceIndex,
) -> EvidenceBundle:
    filters = brief.evidence_filters
    if index.graph_version != brief.graph_version:
        raise ValueError("evidence index graph version does not match brief")
    if filters.graph_version != brief.graph_version:
        raise ValueError("evidence filter graph version does not match brief")
    if filters.concept_id != brief.concept_id or filters.depth is not brief.delivery_depth:
        raise ValueError("evidence filters do not match brief scope")

    selected: dict[str, EvidenceRecord] = {}
    for content_kind in filters.content_kinds:
        matching: list[EvidenceRecord] = []
        for language in filters.languages:
            matching.extend(
                index.query(
                    brief.concept_id,
                    brief.delivery_depth,
                    language,
                    content_kind,
                )
            )
        if not matching:
            raise ValueError(
                "missing published evidence for "
                f"{brief.concept_id}:{brief.delivery_depth.value}:{content_kind.value}"
            )
        for record in matching:
            selected[record.evidence_id] = record

    records = tuple(sorted(selected.values(), key=lambda item: item.evidence_id))
    if len(records) < brief.citation_requirements.min_evidence_records:
        raise ValueError("evidence bundle does not meet minimum record count")
    payload = {
        "brief_id": brief.brief_id,
        "concept_id": brief.concept_id,
        "depth": brief.delivery_depth.value,
        "graph_version": brief.graph_version,
        "records": [record.model_dump(mode="json") for record in records],
    }
    return EvidenceBundle(
        bundle_id=f"bundle_{_hash(payload)}",
        brief_id=brief.brief_id,
        graph_version=brief.graph_version,
        concept_id=brief.concept_id,
        depth=brief.delivery_depth,
        records=records,
    )


def _hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
