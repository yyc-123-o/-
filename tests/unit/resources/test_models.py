import pytest
from pydantic import ValidationError

from skillforge_kb.resources.models import (
    AcceptanceChecks,
    CitationRequirements,
    EvidenceFilters,
)


def test_resource_contracts_reject_empty_requirements() -> None:
    with pytest.raises(ValidationError):
        CitationRequirements(min_evidence_records=0)
    with pytest.raises(ValidationError):
        AcceptanceChecks(required_resource_types=())
    with pytest.raises(ValidationError):
        EvidenceFilters(concept_id="", graph_version="ai-course-v1")
