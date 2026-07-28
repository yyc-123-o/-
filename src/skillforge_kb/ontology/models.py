from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

CONCEPT_ID_PATTERN = r"^[a-z0-9][a-z0-9.-]+$"
GRAPH_ID_PATTERN = r"^[a-z0-9][a-z0-9.-]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class DepthLevel(StrEnum):
    INTRO = "intro"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RelationKind(StrEnum):
    HARD_PREREQUISITE = "hard_prerequisite"
    SOFT_PREREQUISITE = "soft_prerequisite"
    PART_OF = "part_of"
    CONTRASTS_WITH = "contrasts_with"
    CONFUSED_WITH = "confused_with"


class EvidenceStatus(StrEnum):
    CANDIDATE_SUPPORTED = "candidate_supported"
    COVERAGE_GAP = "coverage_gap"
    PUBLISHED = "published"


class GraphReviewStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"


class AssessmentStatus(StrEnum):
    ASSESSED = "assessed"
    NOT_ASSESSED = "not_assessed"


class LocalizedName(BaseModel):
    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)


class ConceptLevel(BaseModel):
    level: DepthLevel
    learning_outcomes: list[str] = Field(min_length=1)
    mastery_threshold: float = Field(ge=0, le=1)
    assessment_kinds: list[str] = Field(min_length=1)


class Course(BaseModel):
    id: str = Field(pattern=GRAPH_ID_PATTERN)
    title: LocalizedName
    audience: str = Field(min_length=1)
    version: str = Field(min_length=1)
    review_status: GraphReviewStatus


class Chapter(BaseModel):
    id: str = Field(pattern=GRAPH_ID_PATTERN)
    order: int = Field(ge=1)
    title: LocalizedName
    summary: str = Field(min_length=2)
    learning_outcomes: list[str] = Field(min_length=2)
    core: bool
    review_status: GraphReviewStatus


class Section(BaseModel):
    id: str = Field(pattern=GRAPH_ID_PATTERN)
    chapter_id: str = Field(pattern=GRAPH_ID_PATTERN)
    order: int = Field(ge=1)
    title: LocalizedName
    learning_outcomes: list[str] = Field(min_length=1)
    review_status: GraphReviewStatus


class Concept(BaseModel):
    id: str = Field(pattern=CONCEPT_ID_PATTERN)
    names: LocalizedName
    aliases: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=2)
    difficulty: int = Field(ge=1, le=4)
    required: bool
    evidence_status: EvidenceStatus
    review_status: GraphReviewStatus
    levels: list[ConceptLevel]

    @model_validator(mode="after")
    def validate_levels(self) -> "Concept":
        if [item.level for item in self.levels] != list(DepthLevel):
            raise ValueError("concept requires exactly one of each depth level in enum order")
        return self


class TeachingAssignment(BaseModel):
    section_id: str = Field(pattern=GRAPH_ID_PATTERN)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    order: int = Field(ge=1)
    required: bool
    review_status: GraphReviewStatus


class Relation(BaseModel):
    source: str = Field(pattern=CONCEPT_ID_PATTERN)
    target: str = Field(pattern=CONCEPT_ID_PATTERN)
    kind: RelationKind
    min_mastery: float | None = Field(default=None, ge=0, le=1)
    review_status: GraphReviewStatus

    @model_validator(mode="after")
    def validate_prerequisite_threshold(self) -> "Relation":
        prerequisite = self.kind in {
            RelationKind.HARD_PREREQUISITE,
            RelationKind.SOFT_PREREQUISITE,
        }
        if prerequisite != (self.min_mastery is not None):
            raise ValueError("only prerequisite relations require min_mastery")
        if self.source == self.target:
            raise ValueError("relations cannot be self-referential")
        return self


class CourseDocument(BaseModel):
    version: str = Field(min_length=1)
    course: Course
    chapters: list[Chapter] = Field(min_length=1)
    sections: list[Section] = Field(min_length=1)
    concepts: list[Concept] = Field(min_length=1)
    teaches: list[TeachingAssignment] = Field(min_length=1)


class RelationDocument(BaseModel):
    version: str = Field(min_length=1)
    relations: list[Relation] = Field(default_factory=list)


class ProfileIdMapping(BaseModel):
    legacy_id: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    graph_version: str = Field(min_length=1)
    reviewed_by: str = Field(min_length=1)


class ProfileMappingDocument(BaseModel):
    version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    mappings: list[ProfileIdMapping] = Field(default_factory=list)


class KnowledgeMastery(BaseModel):
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    mastery_score: float | None = Field(default=None, ge=0, le=1)
    assessment_status: AssessmentStatus
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assessment_state(self) -> "KnowledgeMastery":
        if (
            self.assessment_status is AssessmentStatus.NOT_ASSESSED
            and self.mastery_score is not None
        ):
            raise ValueError("not_assessed mastery must not have a score")
        if self.assessment_status is AssessmentStatus.ASSESSED and self.mastery_score is None:
            raise ValueError("assessed mastery requires a score")
        return self


class AbilityScore(BaseModel):
    score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    assessment_run_id: str = Field(min_length=1)


class ErrorPattern(BaseModel):
    code: str = Field(min_length=1)
    count: int = Field(ge=0)
    ratio: float = Field(ge=0, le=1)
    concept_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class LearningPreferences(BaseModel):
    content_order: list[str] = Field(default_factory=list)
    code_language: str | None = None
    framework: str | None = None
    presentation: list[str] = Field(default_factory=list)
    pace_hours_per_week: float | None = Field(default=None, gt=0)
    project_orientation: str | None = None


class LearnerProfileSnapshot(BaseModel):
    schema_version: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    learner_ref: str = Field(pattern=SHA256_PATTERN)
    graph_version: str = Field(min_length=1)
    observed_at: datetime | None = None
    generated_at: datetime | None = None
    assessment_runs: list[str] = Field(default_factory=list)
    knowledge_mastery: list[KnowledgeMastery] = Field(default_factory=list)
    abilities: dict[str, AbilityScore] = Field(default_factory=dict)
    error_patterns: list[ErrorPattern] = Field(default_factory=list)
    preferences: LearningPreferences = Field(default_factory=LearningPreferences)


class GraphValidationReport(BaseModel):
    version: str = Field(min_length=1)
    chapter_count: int = Field(ge=0)
    section_count: int = Field(ge=0)
    concept_count: int = Field(ge=0)
    teaching_assignment_count: int = Field(ge=0)
    relation_counts: dict[str, int] = Field(default_factory=dict)
    root_ids: list[str] = Field(default_factory=list)
    key_path_ids: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    graph_version: str = Field(min_length=1)
    candidate_counts: dict[str, int] = Field(default_factory=dict)
    coverage_gap_ids: list[str] = Field(default_factory=list)
    unknown_concept_ids: list[str] = Field(default_factory=list)
    invalid_json_lines: list[int] = Field(default_factory=list)
    published_concept_ids: tuple[str, ...] = ()
