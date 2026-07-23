from skillforge_kb.domain.enums import ReviewStatus
from skillforge_kb.domain.models import SourceRecord
from skillforge_kb.domain.ports import SourceRepository

from .policy import SourcePolicy


class SourceGovernanceService:
    def __init__(self, repository: SourceRepository, policy: SourcePolicy) -> None:
        self.repository = repository
        self.policy = policy

    def register(self, source: SourceRecord) -> None:
        if self.repository.get(source.source_id) is not None:
            raise ValueError(f"source already exists: {source.source_id}")
        self.repository.save(source)

    def transition(self, source_id: str, target: ReviewStatus) -> SourceRecord:
        source = self.repository.get(source_id)
        if source is None:
            raise KeyError(source_id)
        self.policy.assert_transition(source.review_status, target)
        updated = source.model_copy(update={"review_status": target})
        self.repository.save(updated)
        return updated
