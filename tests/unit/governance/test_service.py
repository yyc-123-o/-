from datetime import UTC, datetime

import pytest

from skillforge_kb.domain.enums import Language, LicenseStatus, ReviewStatus, SourceTier
from skillforge_kb.domain.models import SourceRecord
from skillforge_kb.governance.policy import SourcePolicy
from skillforge_kb.governance.service import SourceGovernanceService
from skillforge_kb.storage.memory import InMemorySourceRepository


def source(source_id: str = "source-1") -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        title="Open course",
        canonical_url=f"https://example.edu/{source_id}",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=LicenseStatus.ALLOWED,
        license_url="https://example.edu/license",
        retrieved_at=datetime.now(UTC),
    )


def service(repository: InMemorySourceRepository) -> SourceGovernanceService:
    return SourceGovernanceService(repository, SourcePolicy())


def test_register_rejects_duplicate_source_id() -> None:
    repository = InMemorySourceRepository()
    governance = service(repository)
    governance.register(source())

    with pytest.raises(ValueError, match="source already exists: source-1"):
        governance.register(source())


def test_transition_updates_and_persists_review_status() -> None:
    repository = InMemorySourceRepository()
    governance = service(repository)
    governance.register(source())

    updated = governance.transition("source-1", ReviewStatus.LICENSED)

    assert updated.review_status is ReviewStatus.LICENSED
    assert repository.get("source-1") == updated


def test_transition_rejects_unknown_source() -> None:
    governance = service(InMemorySourceRepository())

    with pytest.raises(KeyError, match="source-1"):
        governance.transition("source-1", ReviewStatus.LICENSED)


def test_repository_lists_sources_by_id() -> None:
    repository = InMemorySourceRepository()
    repository.save(source("source-2"))
    repository.save(source("source-1"))

    assert [item.source_id for item in repository.list_all()] == ["source-1", "source-2"]
