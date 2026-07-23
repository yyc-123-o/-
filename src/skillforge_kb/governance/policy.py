from enum import StrEnum

from skillforge_kb.domain.enums import LicenseStatus, ReviewStatus
from skillforge_kb.domain.models import SourceRecord


class AdmissionDecision(StrEnum):
    FULL_TEXT = "full_text"
    METADATA_ONLY = "metadata_only"
    REJECT = "reject"


ALLOWED_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.CANDIDATE: {ReviewStatus.LICENSED},
    ReviewStatus.LICENSED: {ReviewStatus.PARSED},
    ReviewStatus.PARSED: {ReviewStatus.AUTO_CHECKED},
    ReviewStatus.AUTO_CHECKED: {ReviewStatus.HUMAN_REVIEWED},
    ReviewStatus.HUMAN_REVIEWED: {ReviewStatus.PUBLISHED},
    ReviewStatus.PUBLISHED: {ReviewStatus.DEPRECATED},
    ReviewStatus.DEPRECATED: set(),
}


class SourcePolicy:
    def evaluate(self, source: SourceRecord) -> AdmissionDecision:
        if source.license_status is LicenseStatus.ALLOWED:
            return AdmissionDecision.FULL_TEXT
        if source.license_status is LicenseStatus.METADATA_ONLY:
            return AdmissionDecision.METADATA_ONLY
        return AdmissionDecision.REJECT

    def assert_transition(self, current: ReviewStatus, target: ReviewStatus) -> None:
        if target not in ALLOWED_TRANSITIONS[current]:
            raise ValueError(
                f"invalid source transition: {current} -> {target}; human_reviewed required"
            )
