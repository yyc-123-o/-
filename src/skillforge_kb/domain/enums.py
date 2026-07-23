from enum import StrEnum


class Language(StrEnum):
    ZH = "zh"
    EN = "en"


class SourceTier(StrEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class LicenseStatus(StrEnum):
    PENDING = "pending"
    ALLOWED = "allowed"
    METADATA_ONLY = "metadata_only"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    LICENSED = "licensed"
    PARSED = "parsed"
    AUTO_CHECKED = "auto_checked"
    HUMAN_REVIEWED = "human_reviewed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ContentKind(StrEnum):
    DEFINITION = "definition"
    DERIVATION = "derivation"
    CODE = "code"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    MISCONCEPTION = "misconception"
