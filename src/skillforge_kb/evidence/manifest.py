from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import DepthLevel

from .models import EvidenceRecord, EvidenceReviewStatus


class EvidenceIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    records: tuple[EvidenceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_unique_records(self) -> "EvidenceIndex":
        ids = [record.evidence_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique")
        return self

    def query(
        self,
        concept_id: str,
        depth: DepthLevel,
        language: Language | None = None,
        content_kind: ContentKind | None = None,
    ) -> tuple[EvidenceRecord, ...]:
        rows = [
            record
            for record in self.records
            if record.concept_id == concept_id
            and record.depth is depth
            and record.review_status is EvidenceReviewStatus.PUBLISHED
            and record.license_status is LicenseStatus.ALLOWED
            and (language is None or record.language is language)
            and (content_kind is None or record.content_kind is content_kind)
        ]
        return tuple(sorted(rows, key=lambda record: record.evidence_id))


def load_evidence_index(catalog: OntologyCatalog, path: Path) -> EvidenceIndex:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    index = EvidenceIndex.model_validate(raw)
    if index.graph_version != catalog.course_document.version:
        raise ValueError("evidence graph version does not match catalog")
    known_ids = {concept.id for concept in catalog.concepts()}
    for record in index.records:
        if record.graph_version != index.graph_version:
            raise ValueError(f"evidence graph version mismatch: {record.evidence_id}")
        if record.concept_id not in known_ids:
            raise ValueError(f"evidence references unknown concept: {record.concept_id}")
    return index
